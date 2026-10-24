import threading
import time
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app import crud, models, schemas
from app.core.security import get_password_hash
from tests.conftest import login
from tests.test_auth import bearer, claims, refresh

ADMIN = models.UserRole.admin
URL = "/api/auth/users"


def token(client, email):
    return login(client, email).json()["access_token"]


@pytest.fixture
def admin_headers(client, make_user):
    make_user("admin@example.com", role=ADMIN)
    return bearer(token(client, "admin@example.com"))


def emails(response):
    return [u["email"] for u in response.json()["items"]]


# --- права ---


def test_list_without_token(client):
    assert client.get(URL).status_code == 401


def test_list_user_is_forbidden(client, make_user):
    make_user("user@example.com")
    r = client.get(URL, headers=bearer(token(client, "user@example.com")))
    assert r.status_code == 403
    assert r.json()["detail"] == "Admin role required"


def test_list_admin_by_token_but_demoted_in_db_is_forbidden(client, make_user, db):
    admin = make_user("admin@example.com", role=ADMIN)
    headers = bearer(token(client, "admin@example.com"))
    assert client.get(URL, headers=headers).status_code == 200
    # токен ещё несёт роль admin, но в базе её уже нет
    admin.role = models.UserRole.user
    db.commit()
    assert client.get(URL, headers=headers).status_code == 403


# --- конверт и пагинация ---


def test_list_envelope_and_user_fields(client, admin_headers, make_user):
    make_user("u1@example.com", full_name="Ivan")
    r = client.get(URL, headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert (body["total"], body["limit"], body["offset"]) == (2, 50, 0)
    assert set(body["items"][0]) == {
        "id",
        "email",
        "full_name",
        "role",
        "is_active",
        "created_at",
    }
    assert "hashed_password" not in body["items"][0]


def test_list_total_ignores_limit_and_offset(client, admin_headers, make_user):
    for i in range(4):
        make_user(f"u{i}@example.com")
    r = client.get(URL, params={"limit": 2, "offset": 3, "sort": "email"}, headers=admin_headers)
    assert r.json()["total"] == 5
    assert emails(r) == ["u2@example.com", "u3@example.com"]
    assert (r.json()["limit"], r.json()["offset"]) == (2, 3)


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 201},
        {"offset": -1},
        {"sort": "role"},
        {"sort": "-role"},
        {"role": "root"},
        {"is_active": "maybe"},
        {"q": ""},
        {"q": "x" * 101},
        {"id": "abc"},
    ],
)
def test_list_bad_params_are_422(client, admin_headers, params):
    assert client.get(URL, params=params, headers=admin_headers).status_code == 422


def test_list_limit_bounds_are_accepted(client, admin_headers):
    assert client.get(URL, params={"limit": 1}, headers=admin_headers).status_code == 200
    assert client.get(URL, params={"limit": 200}, headers=admin_headers).status_code == 200
    assert client.get(URL, params={"q": "x" * 100}, headers=admin_headers).status_code == 200


# --- сортировка ---


def test_list_default_sort_is_newest_first(client, admin_headers, make_user):
    now = datetime.now(UTC)
    make_user("old@example.com", created_at=now - timedelta(days=2))
    make_user("new@example.com", created_at=now + timedelta(days=2))
    assert emails(client.get(URL, headers=admin_headers)) == [
        "new@example.com",
        "admin@example.com",
        "old@example.com",
    ]


def test_list_sort_created_at_both_directions(client, admin_headers, make_user):
    now = datetime.now(UTC)
    make_user("b@example.com", created_at=now - timedelta(days=1))
    make_user("a@example.com", created_at=now - timedelta(days=2))
    make_user("c@example.com", created_at=now + timedelta(days=1))
    asc = emails(client.get(URL, params={"sort": "created_at"}, headers=admin_headers))
    desc = emails(client.get(URL, params={"sort": "-created_at"}, headers=admin_headers))
    assert asc == ["a@example.com", "b@example.com", "admin@example.com", "c@example.com"]
    assert desc == asc[::-1]


def test_list_sort_email_both_directions(client, admin_headers, make_user):
    for name in ("c", "a", "b"):
        make_user(f"{name}@example.com")
    asc = emails(client.get(URL, params={"sort": "email"}, headers=admin_headers))
    desc = emails(client.get(URL, params={"sort": "-email"}, headers=admin_headers))
    assert asc == ["a@example.com", "admin@example.com", "b@example.com", "c@example.com"]
    assert desc == asc[::-1]


def test_list_equal_sort_key_is_ordered_by_id(client, admin_headers, make_user):
    same = datetime(2026, 1, 1, tzinfo=UTC)
    users = [make_user(f"s{i}@example.com", created_at=same) for i in range(3)]
    ids = [u.id for u in users]
    asc = client.get(URL, params={"sort": "created_at", "q": "s"}, headers=admin_headers)
    desc = client.get(URL, params={"sort": "-created_at", "q": "s"}, headers=admin_headers)
    assert [u["id"] for u in asc.json()["items"]] == ids
    assert [u["id"] for u in desc.json()["items"]] == ids[::-1]
    # страницы не теряют и не дублируют строки с одинаковым ключом
    pages = [
        client.get(
            URL,
            params={"sort": "created_at", "q": "s", "limit": 1, "offset": i},
            headers=admin_headers,
        )
        for i in range(3)
    ]
    assert [p.json()["items"][0]["id"] for p in pages] == ids


# --- фильтры ---


def test_list_filter_by_role(client, admin_headers, make_user):
    make_user("u@example.com")
    r = client.get(URL, params={"role": "admin"}, headers=admin_headers)
    assert emails(r) == ["admin@example.com"]
    assert r.json()["total"] == 1
    assert emails(client.get(URL, params={"role": "user"}, headers=admin_headers)) == [
        "u@example.com"
    ]


def test_list_filter_by_is_active(client, admin_headers, make_user):
    make_user("off@example.com", is_active=False)
    off = client.get(URL, params={"is_active": "false"}, headers=admin_headers)
    on = client.get(URL, params={"is_active": "true"}, headers=admin_headers)
    assert emails(off) == ["off@example.com"]
    assert emails(on) == ["admin@example.com"]


def test_list_filters_combine(client, admin_headers, make_user):
    make_user("ann@example.com", full_name="Ann")
    make_user("ann-off@example.com", full_name="Ann", is_active=False)
    make_user("bob@example.com", full_name="Bob")
    make_user("root-off@example.com", role=ADMIN, is_active=False)
    r = client.get(
        URL,
        params={"role": "user", "is_active": "true", "q": "ann", "sort": "email"},
        headers=admin_headers,
    )
    assert emails(r) == ["ann@example.com"]
    assert r.json()["total"] == 1
    r = client.get(URL, params={"role": "admin", "is_active": "false"}, headers=admin_headers)
    assert emails(r) == ["root-off@example.com"]


def test_list_q_matches_email_and_name_case_insensitively(client, admin_headers, make_user):
    make_user("alice@example.com", full_name="Zed Smith")
    make_user("bob@example.com", full_name="Alice Cooper")
    make_user("carol@example.com", full_name=None)
    r = client.get(URL, params={"q": "ALICE", "sort": "email"}, headers=admin_headers)
    assert emails(r) == ["alice@example.com", "bob@example.com"]
    assert emails(client.get(URL, params={"q": "smith"}, headers=admin_headers)) == [
        "alice@example.com"
    ]
    assert client.get(URL, params={"q": "nobody"}, headers=admin_headers).json()["total"] == 0


@pytest.mark.parametrize(
    ("q", "match", "other"),
    [
        ("100%", "100% done", "1000 done"),
        ("a_c", "a_c", "abc"),
        ("a\\c", "a\\c", "ac"),
        ("%", "50%", "plain"),
    ],
)
def test_list_q_wildcards_are_plain_characters(client, admin_headers, make_user, q, match, other):
    # имя, а не email: в ответе email проходит проверку EmailStr, а \ в адресе недопустим
    make_user("match@example.com", full_name=match)
    make_user("other@example.com", full_name=other)
    r = client.get(URL, params={"q": q}, headers=admin_headers)
    assert emails(r) == ["match@example.com"]
    assert r.json()["total"] == 1


def test_list_id_is_repeatable(client, admin_headers, make_user):
    u1 = make_user("u1@example.com")
    u2 = make_user("u2@example.com")
    make_user("u3@example.com")
    r = client.get(URL, params={"id": [u1.id, u2.id], "sort": "email"}, headers=admin_headers)
    assert emails(r) == ["u1@example.com", "u2@example.com"]
    assert r.json()["total"] == 2


def test_list_id_unknown_is_just_missing(client, admin_headers, make_user):
    u1 = make_user("u1@example.com")
    r = client.get(URL, params={"id": [u1.id, 99999]}, headers=admin_headers)
    assert emails(r) == ["u1@example.com"]
    assert r.json()["total"] == 1


def test_list_id_with_other_filters_and_inactive_users(client, admin_headers, make_user):
    off = make_user("off@example.com", is_active=False)
    on = make_user("on@example.com")
    both = client.get(URL, params={"id": [off.id, on.id], "sort": "email"}, headers=admin_headers)
    assert emails(both) == ["off@example.com", "on@example.com"]
    only_off = client.get(
        URL, params={"id": [off.id, on.id], "is_active": "false"}, headers=admin_headers
    )
    assert emails(only_off) == ["off@example.com"]


def test_list_id_limit_is_200(client, admin_headers):
    assert (
        client.get(URL, params={"id": list(range(1, 201))}, headers=admin_headers).status_code
        == 200
    )
    r = client.get(URL, params={"id": list(range(1, 202))}, headers=admin_headers)
    assert r.status_code == 422


# --- read-модели ---


def test_me_and_register_return_created_at(client, make_user):
    r = client.post(
        "/api/auth/register", json={"email": "new@example.com", "password": "password123"}
    )
    assert r.status_code == 201
    assert r.json()["created_at"]
    me = client.get("/api/auth/me", headers=bearer(token(client, "new@example.com")))
    assert me.json()["created_at"] == r.json()["created_at"]


# --- PostgreSQL ---


def test_list_q_finds_cyrillic_in_other_case_on_postgres(pg_app, client):
    # lower() SQLite не приводит не-ASCII, поэтому такой поиск проверяется только на PostgreSQL
    with sessionmaker(bind=pg_app.engine)() as session:
        session.add_all(
            [
                models.User(
                    email="admin@example.com",
                    hashed_password=get_password_hash("password123"),
                    role=ADMIN,
                ),
                models.User(
                    email="ivan@example.com",
                    hashed_password=get_password_hash("password123"),
                    full_name="Иван Петров",
                ),
                models.User(
                    email="olga@example.com",
                    hashed_password=get_password_hash("password123"),
                    full_name="Ольга",
                ),
            ]
        )
        session.commit()
    headers = bearer(token(client, "admin@example.com"))
    r = client.get(URL, params={"q": "иВАН"}, headers=headers)
    assert emails(r) == ["ivan@example.com"]
    assert emails(client.get(URL, params={"q": "ПЕТРОВ"}, headers=headers)) == ["ivan@example.com"]
    # фильтр по нативному enum PostgreSQL
    assert emails(client.get(URL, params={"role": "admin"}, headers=headers)) == [
        "admin@example.com"
    ]


# --- PATCH: роль и отключение ---


def patch(client, headers, user_id, body):
    return client.patch(f"{URL}/{user_id}", json=body, headers=headers)


def audit_rows(db):
    db.expire_all()
    rows = db.scalars(select(models.UserAudit).order_by(models.UserAudit.id))
    return [(r.actor_id, r.target_id, r.field, r.old_value, r.new_value) for r in rows]


def test_patch_without_token(client, make_user):
    u = make_user("u@example.com")
    assert client.patch(f"{URL}/{u.id}", json={"role": "admin"}).status_code == 401


def test_patch_user_is_forbidden(client, make_user):
    make_user("user@example.com")
    other = make_user("other@example.com")
    headers = bearer(token(client, "user@example.com"))
    r = patch(client, headers, other.id, {"is_active": False})
    assert r.status_code == 403
    assert r.json()["detail"] == "Admin role required"


def test_patch_admin_by_token_but_demoted_in_db_is_forbidden(client, make_user, db):
    admin = make_user("admin@example.com", role=ADMIN)
    make_user("admin2@example.com", role=ADMIN)
    target = make_user("u@example.com")
    headers = bearer(token(client, "admin@example.com"))
    admin.role = models.UserRole.user
    db.commit()
    assert patch(client, headers, target.id, {"is_active": False}).status_code == 403
    db.refresh(target)
    assert target.is_active is True
    assert audit_rows(db) == []


def test_patch_actor_demoted_while_waiting_for_lock_is_forbidden(
    client, admin_headers, make_user, db, monkeypatch
):
    # на SQLite гонки нет: набор после блокировки подменяется — автора в нём уже нет
    other_admin = make_user("admin2@example.com", role=ADMIN)
    target = make_user("u@example.com")
    monkeypatch.setattr(crud, "lock_active_admin_ids", lambda db: {other_admin.id})
    r = patch(client, admin_headers, target.id, {"role": "admin"})
    assert r.status_code == 403
    assert r.json()["detail"] == "Admin role required"
    db.refresh(target)
    assert target.role == models.UserRole.user
    assert audit_rows(db) == []


@pytest.mark.parametrize("body", [{"is_active": False}, {}])
def test_patch_unknown_user_is_404(client, admin_headers, body):
    r = patch(client, admin_headers, 99999, body)
    assert r.status_code == 404
    assert r.json()["detail"] == "User not found"


def test_delete_user_is_405(client, admin_headers, make_user):
    u = make_user("u@example.com")
    assert client.delete(f"{URL}/{u.id}", headers=admin_headers).status_code == 405


@pytest.mark.parametrize("body", [{"role": "user"}, {"is_active": False}, {"role": "admin"}])
def test_patch_self_is_409(client, make_user, db, body):
    admin = make_user("admin@example.com", role=ADMIN)
    make_user("admin2@example.com", role=ADMIN)
    r = patch(client, bearer(token(client, "admin@example.com")), admin.id, body)
    assert r.status_code == 409
    assert r.json()["detail"] == "Cannot change your own role or status"
    assert audit_rows(db) == []


def test_patch_self_with_empty_body_returns_self(client, make_user):
    admin = make_user("admin@example.com", role=ADMIN)
    r = patch(client, bearer(token(client, "admin@example.com")), admin.id, {})
    assert r.status_code == 200
    assert r.json()["email"] == "admin@example.com"


@pytest.mark.parametrize(
    "body",
    [
        {"role": None},
        {"is_active": None},
        {"role": "root"},
        {"is_active": "maybe"},
        {"full_name": "x"},
        {"email": "new@example.com"},
        {"role": "admin", "rol": "user"},
    ],
)
def test_patch_bad_body_is_422(client, admin_headers, make_user, db, body):
    u = make_user("u@example.com")
    assert patch(client, admin_headers, u.id, body).status_code == 422
    db.refresh(u)
    assert (u.role, u.is_active, u.full_name) == (models.UserRole.user, True, None)
    assert audit_rows(db) == []


def test_patch_empty_body_changes_nothing(client, admin_headers, make_user, db):
    u = make_user("u@example.com", full_name="Ann")
    r = patch(client, admin_headers, u.id, {})
    assert r.status_code == 200
    assert (r.json()["role"], r.json()["is_active"]) == ("user", True)
    assert audit_rows(db) == []


def test_patch_promote_and_demote(client, admin_headers, make_user, db):
    u = make_user("u@example.com")
    r = patch(client, admin_headers, u.id, {"role": "admin"})
    assert r.status_code == 200
    assert set(r.json()) == {"id", "email", "full_name", "role", "is_active", "created_at"}
    assert r.json()["role"] == "admin"
    db.refresh(u)
    assert u.role == ADMIN
    # повышенный сразу admin в auth: роль берётся из базы, токен тот же
    u_headers = bearer(token(client, "u@example.com"))
    assert client.get(URL, headers=u_headers).status_code == 200

    r = patch(client, admin_headers, u.id, {"role": "user"})
    assert r.json()["role"] == "user"
    assert client.get(URL, headers=u_headers).status_code == 403


def test_patch_new_role_in_token_after_refresh(client, admin_headers, make_user):
    u = make_user("u@example.com")
    tokens = login(client, "u@example.com").json()
    assert claims(tokens["access_token"])["role"] == "user"
    patch(client, admin_headers, u.id, {"role": "admin"})
    r = refresh(client, tokens["refresh_token"])
    assert claims(r.json()["access_token"])["role"] == "admin"


def test_patch_disable_and_enable(client, admin_headers, make_user):
    u = make_user("u@example.com")
    tokens = login(client, "u@example.com").json()
    u_headers = bearer(tokens["access_token"])
    r = patch(client, admin_headers, u.id, {"is_active": False})
    assert r.status_code == 200
    assert r.json()["is_active"] is False
    # отключённый теряет доступ к auth сразу, не дожидаясь истечения токена
    assert client.get("/api/auth/me", headers=u_headers).status_code == 401
    assert refresh(client, tokens["refresh_token"]).status_code == 401
    assert login(client, "u@example.com").status_code == 403

    assert patch(client, admin_headers, u.id, {"is_active": True}).json()["is_active"] is True
    assert client.get("/api/auth/me", headers=u_headers).status_code == 200
    assert login(client, "u@example.com").status_code == 200


def test_patch_other_admin_can_be_demoted_and_disabled(client, admin_headers, make_user, db):
    other = make_user("admin2@example.com", role=ADMIN)
    r = patch(client, admin_headers, other.id, {"role": "user", "is_active": False})
    assert r.status_code == 200
    assert (r.json()["role"], r.json()["is_active"]) == ("user", False)
    active_admins = db.scalars(
        select(models.User.email).where(models.User.role == ADMIN, models.User.is_active)
    ).all()
    assert active_admins == ["admin@example.com"]


def test_patch_audit_row_per_changed_field(client, make_user, db):
    admin = make_user("admin@example.com", role=ADMIN)
    headers = bearer(token(client, "admin@example.com"))
    u = make_user("u@example.com")
    patch(client, headers, u.id, {"role": "admin", "is_active": False})
    assert audit_rows(db) == [
        (admin.id, u.id, "role", "user", "admin"),
        (admin.id, u.id, "is_active", "true", "false"),
    ]
    # одно поле совпадает с текущим: строка только на изменённое
    patch(client, headers, u.id, {"role": "admin", "is_active": True})
    assert audit_rows(db)[2:] == [(admin.id, u.id, "is_active", "false", "true")]
    # ничего не меняется — строк нет
    assert patch(client, headers, u.id, {"role": "admin", "is_active": True}).status_code == 200
    assert len(audit_rows(db)) == 3
    rows = db.scalars(select(models.UserAudit)).all()
    assert all(r.created_at is not None for r in rows)


# --- PATCH на PostgreSQL ---


def test_parallel_demote_on_postgres_keeps_one_admin(pg_app, monkeypatch):
    """Два admin одновременно понижают друг друга: второй ждёт блокировку и получает 403."""
    Session = sessionmaker(autoflush=False, bind=pg_app.engine)
    with Session() as db:
        a = models.User(email="a@example.com", hashed_password="x", role=ADMIN)
        b = models.User(email="b@example.com", hashed_password="x", role=ADMIN)
        db.add_all([a, b])
        db.commit()
        ids = {"a": a.id, "b": b.id}

    # оба запроса подходят к блокировке одновременно и держат набор admin 0,3 с:
    # без FOR UPDATE оба видят двух admin и понижают друг друга
    barrier = threading.Barrier(2)
    real_lock = crud.lock_active_admin_ids

    def lock_together(db):
        barrier.wait(5)
        locked = real_lock(db)
        time.sleep(0.3)
        return locked

    monkeypatch.setattr(crud, "lock_active_admin_ids", lock_together)
    results = {}

    def demote(actor, target):
        with Session() as db:
            actor_user = db.get(models.User, ids[actor])
            update = schemas.UserAdminUpdate(role="user")
            try:
                crud.update_user_by_admin(db, actor_user, ids[target], update)
                results[actor] = 200
            except HTTPException as exc:
                results[actor] = exc.status_code

    threads = [
        threading.Thread(target=demote, args=("a", "b")),
        threading.Thread(target=demote, args=("b", "a")),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)

    assert sorted(results.values()) == [200, 403]
    with Session() as db:
        admins = db.scalars(
            select(models.User.id).where(models.User.role == ADMIN, models.User.is_active)
        ).all()
        winner = next(k for k, v in results.items() if v == 200)
        assert admins == [ids[winner]]
        assert db.scalar(select(func.count()).select_from(models.UserAudit)) == 1
