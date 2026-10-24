from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import sessionmaker

from app import models
from app.core.security import get_password_hash
from tests.conftest import login
from tests.test_auth import bearer

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
