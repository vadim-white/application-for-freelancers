import os
import pathlib
import subprocess
import sys
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from .conftest import auth, make_token

SERVICE_ROOT = pathlib.Path(__file__).resolve().parent.parent

PROTECTED = [
    ("get", "/api/time/time-entries"),
    ("post", "/api/time/time-entries"),
    ("patch", "/api/time/time-entries/1"),
    ("delete", "/api/time/time-entries/1"),
    ("get", "/api/time/statistics/users"),
]


@pytest.mark.parametrize("method,path", PROTECTED)
def test_protected_without_token_401(client, method, path):
    r = client.request(method, path, json={})
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


def test_root_is_public(client):
    assert client.get("/").status_code == 200


@pytest.mark.parametrize(
    "token",
    [
        make_token(expires_in=timedelta(minutes=-1)),
        make_token(exp=False),
        make_token(token_type="refresh"),
        make_token(secret="other-secret-key-at-least-32-bytes-long"),
        make_token(sub="abc"),
        make_token(role="superuser"),
        "not-a-jwt",
    ],
)
def test_invalid_tokens_401(client, token):
    assert client.get("/api/time/time-entries", headers=auth(token)).status_code == 401


def test_x_user_headers_without_token_401(client):
    r = client.get("/api/time/time-entries", headers={"X-User-Id": "1", "X-User-Role": "admin"})
    assert r.status_code == 401


A = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)


def iso(value):
    return value.isoformat()


def create(client, headers, minutes=10, at=A, **body):
    payload = {
        "task_id": 1,
        "started_at": iso(at),
        "stopped_at": iso(at + timedelta(minutes=minutes)),
        **body,
    }
    return client.post("/api/time/time-entries", json=payload, headers=headers)


def items(client, headers, query=""):
    r = client.get(f"/api/time/time-entries{query}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["items"]


def test_user_id_taken_from_token_not_body(client, user1):
    r = create(client, user1, user_id=2)
    assert r.status_code == 201
    assert r.json()["user_id"] == 1


def test_user_sees_only_own_entries(client, user1, user2):
    create(client, user1)
    create(client, user2)
    create(client, user2)
    assert [e["user_id"] for e in items(client, user1)] == [1]
    assert len(items(client, user2)) == 2


def test_user_cannot_query_other_user(client, user1, user2):
    create(client, user2)
    assert client.get("/api/time/time-entries?user_id=2", headers=user1).status_code == 403
    assert items(client, user1, "?user_id=1") == []


def test_forged_role_header_does_not_grant_admin(client, user1, user2):
    create(client, user2)
    assert items(client, {**user1, "X-User-Role": "admin"}) == []


def test_task_filter_combined_with_own_entries(client, user1, user2):
    create(client, user1, task_id=5)
    create(client, user1, task_id=6)
    create(client, user2, task_id=5)
    assert [(e["task_id"], e["user_id"]) for e in items(client, user1, "?task_id=5")] == [(5, 1)]


def test_admin_sees_all_and_can_filter(client, user1, user2, admin):
    create(client, user1)
    create(client, user2)
    assert len(items(client, admin)) == 2
    assert [e["user_id"] for e in items(client, admin, "?user_id=2")] == [2]


# --- Ручная запись ---


def test_create_fills_duration(client, user1):
    r = create(client, user1, minutes=5, description="manual")
    assert r.status_code == 201
    entry = r.json()
    assert (entry["task_id"], entry["description"]) == (1, "manual")
    assert datetime.fromisoformat(entry["started_at"]) == A
    assert datetime.fromisoformat(entry["stopped_at"]) == A + timedelta(minutes=5)
    assert entry["duration_seconds"] == 300


@pytest.mark.parametrize("seconds", [0, 1, 61.9])
def test_create_any_length_duration_floored(client, user1, seconds):
    body = {"started_at": iso(A), "stopped_at": iso(A + timedelta(seconds=seconds))}
    r = client.post("/api/time/time-entries", json={"task_id": 1, **body}, headers=user1)
    assert r.status_code == 201
    assert r.json()["duration_seconds"] == int(seconds)


def test_create_accepts_time_with_offset(client, user1):
    body = {
        "task_id": 1,
        "started_at": "2026-10-22T15:00:00+03:00",
        "stopped_at": "2026-10-22T15:30:00+03:00",
    }
    entry = client.post("/api/time/time-entries", json=body, headers=user1).json()
    assert datetime.fromisoformat(entry["started_at"]) == A
    assert entry["duration_seconds"] == 1800


def test_create_stopped_before_started_422(client, user1):
    r = create(client, user1, minutes=-1)
    assert r.status_code == 422
    assert items(client, user1) == []


def test_create_in_future_422(client, user1):
    soon = datetime.now(UTC) + timedelta(seconds=30)
    assert create(client, user1, minutes=0, at=soon).status_code == 201
    far = datetime.now(UTC) + timedelta(minutes=5)
    assert create(client, user1, minutes=0, at=far).status_code == 422


@pytest.mark.parametrize(
    "body",
    [
        {"task_id": 1, "minutes": 5},
        {"task_id": 1, "started_at": "2026-10-22T12:00:00Z"},
        {"task_id": 1, "started_at": "2026-10-22T12:00:00", "stopped_at": "2026-10-22T12:10:00"},
        {"started_at": "2026-10-22T12:00:00Z", "stopped_at": "2026-10-22T12:10:00Z"},
    ],
)
def test_create_bad_body_422(client, user1, body):
    assert client.post("/api/time/time-entries", json=body, headers=user1).status_code == 422


def test_create_checks_task(client, user1, task_service):
    task_service.handler = lambda request: httpx.Response(404)
    assert create(client, user1).status_code == 404
    [call] = task_service.calls
    assert call.headers["authorization"] == user1["Authorization"]
    assert items(client, user1) == []


# --- Список: конверт, фильтры, сортировка ---


def seed(client, headers, count=5):
    for i in range(count):
        create(client, headers, minutes=1, at=A + timedelta(hours=i), task_id=1 + i % 2)


def test_list_envelope_and_default_sort(client, user1):
    seed(client, user1)
    body = client.get("/api/time/time-entries", headers=user1).json()
    assert (body["total"], body["limit"], body["offset"]) == (5, 50, 0)
    starts = [datetime.fromisoformat(e["started_at"]) for e in body["items"]]
    assert starts == sorted(starts, reverse=True)


def test_list_sort_ascending(client, user1):
    seed(client, user1)
    starts = [e["started_at"] for e in items(client, user1, "?sort=started_at")]
    assert starts == sorted(starts)


def test_list_pagination(client, user1):
    seed(client, user1)
    page = client.get("/api/time/time-entries?limit=2&offset=2", headers=user1).json()
    assert (page["total"], page["limit"], page["offset"], len(page["items"])) == (5, 2, 2, 2)
    ids = [e["id"] for e in items(client, user1, "?sort=started_at")]
    assert [e["id"] for e in page["items"]] == ids[::-1][2:4]
    assert items(client, user1, "?offset=5") == []


def test_list_ties_ordered_by_id(client, user1):
    for _ in range(3):
        create(client, user1, minutes=1)
    assert [e["id"] for e in items(client, user1)] == [3, 2, 1]
    assert [e["id"] for e in items(client, user1, "?sort=started_at")] == [1, 2, 3]


def test_list_from_to_filter_by_started_at(client, user1):
    seed(client, user1)
    frm, to = iso(A + timedelta(hours=1)), iso(A + timedelta(hours=3))
    # from включительно, to не включительно
    r = client.get("/api/time/time-entries", params={"from": frm, "to": to}, headers=user1)
    assert [e["started_at"] for e in r.json()["items"]] == [
        iso(A + timedelta(hours=2)).replace("+00:00", "Z"),
        iso(A + timedelta(hours=1)).replace("+00:00", "Z"),
    ]
    assert r.json()["total"] == 2


def test_list_filters_combined(client, user1):
    seed(client, user1)
    frm = iso(A + timedelta(hours=1))
    body = client.get(
        "/api/time/time-entries", params={"from": frm, "task_id": 2}, headers=user1
    ).json()
    assert body["total"] == 2
    assert {e["task_id"] for e in body["items"]} == {2}


@pytest.mark.parametrize(
    "query",
    [
        "?sort=minutes",
        "?sort=-id",
        "?limit=201",
        "?limit=0",
        "?offset=-1",
        "?limit=x",
        "?from=2026-10-22T12:00:00",
        "?to=yesterday",
    ],
)
def test_list_bad_query_422(client, user1, query):
    assert client.get(f"/api/time/time-entries{query}", headers=user1).status_code == 422


def test_list_limit_200_allowed(client, user1):
    assert client.get("/api/time/time-entries?limit=200", headers=user1).json()["limit"] == 200


# --- PATCH ---


def patch(client, headers, entry_id, **body):
    return client.patch(f"/api/time/time-entries/{entry_id}", json=body, headers=headers)


def test_patch_description_only_keeps_times(client, user1):
    entry = create(client, user1, minutes=5).json()
    r = patch(client, user1, entry["id"], description="new")
    assert r.status_code == 200
    updated = r.json()
    assert updated["description"] == "new"
    for field in ("started_at", "stopped_at", "duration_seconds", "task_id"):
        assert updated[field] == entry[field]


def test_patch_null_description_clears_it(client, user1):
    entry = create(client, user1, description="x").json()
    assert patch(client, user1, entry["id"], description=None).json()["description"] is None


def test_patch_times_recalculates_duration(client, user1):
    entry = create(client, user1, minutes=5).json()
    r = patch(client, user1, entry["id"], stopped_at=iso(A + timedelta(seconds=125)))
    assert r.json()["duration_seconds"] == 125
    r = patch(client, user1, entry["id"], started_at=iso(A + timedelta(seconds=5)))
    assert r.json()["duration_seconds"] == 120


def test_patch_stopped_before_started_422(client, user1):
    entry = create(client, user1).json()
    assert (
        patch(client, user1, entry["id"], stopped_at=iso(A - timedelta(minutes=1))).status_code
        == 422
    )
    assert (
        patch(client, user1, entry["id"], started_at=iso(A + timedelta(hours=1))).status_code == 422
    )
    assert items(client, user1)[0]["stopped_at"] == entry["stopped_at"]


def test_patch_stopped_in_future_422(client, user1):
    entry = create(client, user1).json()
    future = iso(datetime.now(UTC) + timedelta(minutes=5))
    assert patch(client, user1, entry["id"], stopped_at=future).status_code == 422


@pytest.mark.parametrize("field", ["task_id", "started_at", "stopped_at"])
def test_patch_null_required_field_422(client, user1, field):
    entry = create(client, user1).json()
    assert patch(client, user1, entry["id"], **{field: None}).status_code == 422


@pytest.mark.parametrize("body", [{"descripton": "typo"}, {"user_id": 2}, {"id": 99}])
def test_patch_unknown_field_422(client, user1, body):
    entry = create(client, user1, description="old").json()
    assert patch(client, user1, entry["id"], **body).status_code == 422
    assert patch(client, user1, entry["id"], description="new", **body).status_code == 422
    assert items(client, user1)[0] == entry


def test_patch_empty_body_keeps_entry(client, user1):
    entry = create(client, user1, description="old").json()
    r = patch(client, user1, entry["id"])
    assert (r.status_code, r.json()) == (200, entry)


def test_patch_other_user_entry_404(client, user1, user2):
    entry = create(client, user2).json()
    assert patch(client, user1, entry["id"], description="x").status_code == 404
    assert items(client, user2)[0]["description"] is None
    assert patch(client, user1, 999, description="x").status_code == 404


def test_patch_admin_edits_any_entry(client, user1, admin):
    entry = create(client, user1).json()
    r = patch(client, admin, entry["id"], description="by admin")
    assert r.status_code == 200
    assert (r.json()["user_id"], r.json()["description"]) == (1, "by admin")


def test_patch_task_id_checks_task(client, user1, task_service):
    entry = create(client, user1).json()
    calls = len(task_service.calls)
    r = patch(client, user1, entry["id"], task_id=7)
    assert r.json()["task_id"] == 7
    assert [c.url.path for c in task_service.calls[calls:]] == ["/api/tasks/tasks/7"]
    task_service.handler = lambda request: httpx.Response(404)
    assert patch(client, user1, entry["id"], task_id=8).status_code == 404
    assert items(client, user1)[0]["task_id"] == 7


def test_patch_without_task_id_does_not_call_task(client, user1, task_service):
    entry = create(client, user1).json()
    calls = len(task_service.calls)
    patch(client, user1, entry["id"], description="x", stopped_at=iso(A + timedelta(minutes=1)))
    assert len(task_service.calls) == calls


def test_patch_running_entry(client, user1):
    entry = client.post("/api/time/timer/start", json={"task_id": 1}, headers=user1).json()["entry"]
    assert patch(client, user1, entry["id"], description="during").json()["description"] == "during"
    r = patch(client, user1, entry["id"], stopped_at=iso(datetime.now(UTC)))
    assert r.status_code == 422
    assert client.get("/api/time/timer", headers=user1).json()["entry"]["stopped_at"] is None
    # начало идущей можно сдвинуть: длительность появится при остановке
    earlier = iso(datetime.now(UTC) - timedelta(minutes=10))
    r = patch(client, user1, entry["id"], started_at=earlier)
    assert (r.status_code, r.json()["duration_seconds"]) == (200, None)
    stopped = client.post("/api/time/timer/stop", headers=user1).json()["stopped"]
    assert stopped["duration_seconds"] >= 600


# --- DELETE ---


def test_delete_own_entry_204(client, user1):
    entry = create(client, user1).json()
    r = client.delete(f"/api/time/time-entries/{entry['id']}", headers=user1)
    assert (r.status_code, r.content) == (204, b"")
    assert items(client, user1) == []
    assert client.delete(f"/api/time/time-entries/{entry['id']}", headers=user1).status_code == 404


def test_delete_other_user_entry_404(client, user1, user2):
    entry = create(client, user2).json()
    assert client.delete(f"/api/time/time-entries/{entry['id']}", headers=user1).status_code == 404
    assert len(items(client, user2)) == 1


def test_delete_admin_deletes_any(client, user1, admin):
    entry = create(client, user1).json()
    assert client.delete(f"/api/time/time-entries/{entry['id']}", headers=admin).status_code == 204
    assert items(client, user1) == []


def test_delete_running_entry_stops_timer(client, user1):
    entry = client.post("/api/time/timer/start", json={"task_id": 1}, headers=user1).json()["entry"]
    assert client.delete(f"/api/time/time-entries/{entry['id']}", headers=user1).status_code == 204
    assert client.get("/api/time/timer", headers=user1).json()["entry"] is None
    assert client.post("/api/time/timer/stop", headers=user1).json()["stopped"] is None


# --- Статистика ---


def test_statistics_admin_only(client, user1, admin):
    assert client.get("/api/time/statistics/users", headers=user1).status_code == 403
    assert client.get("/api/time/statistics/users", headers=admin).json() == []


def test_statistics_fields(client, user1, user2, admin):
    create(client, user1, minutes=10, task_id=1)
    create(client, user1, minutes=20, task_id=1)
    create(client, user1, minutes=30, task_id=2)
    create(client, user2, minutes=1, task_id=3)
    r = client.get("/api/time/statistics/users", headers=admin)
    assert r.status_code == 200
    assert r.json() == [
        {
            "user_id": 1,
            "entries_count": 3,
            "tasks_count": 2,
            "total_seconds": 3600,
            "avg_seconds_per_task": 1800,
        },
        {
            "user_id": 2,
            "entries_count": 1,
            "tasks_count": 1,
            "total_seconds": 60,
            "avg_seconds_per_task": 60,
        },
    ]


def test_statistics_count_only_closed_entries(client, user1, admin):
    create(client, user1, minutes=2)
    client.post("/api/time/timer/start", json={"task_id": 2}, headers=user1)
    [row] = client.get("/api/time/statistics/users", headers=admin).json()
    assert (row["entries_count"], row["tasks_count"], row["total_seconds"]) == (1, 1, 120)


def test_statistics_zero_length_entry(client, user1, admin):
    create(client, user1, minutes=0)
    [row] = client.get("/api/time/statistics/users", headers=admin).json()
    assert (row["entries_count"], row["total_seconds"], row["avg_seconds_per_task"]) == (1, 0, 0)


# --- Проекты удалены из time (проекты живут в task-service) ---


@pytest.mark.parametrize("method", ["get", "post"])
def test_projects_endpoint_removed_404(client, user1, method):
    r = client.request(method, "/api/time/projects", json={"name": "p"}, headers=user1)
    assert r.status_code == 404


# --- DATABASE_URL обязателен ---


def test_settings_require_database_url(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    env["SECRET_KEY"] = "test-secret"
    env["PYTHONPATH"] = str(SERVICE_ROOT)
    # cwd без .env, иначе строка подключения подтянется оттуда
    r = subprocess.run(
        [sys.executable, "-c", "import app.core.config"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert r.returncode != 0
    assert "DATABASE_URL" in r.stderr


def test_pool_reconnects_after_database_restart(pg_app, client, user1):
    assert client.get("/api/time/time-entries", headers=user1).status_code == 200
    # соединение осталось в пуле, а база его закрыла: без pre-ping первый запрос получил бы 500
    assert pg_app.terminate() >= 1
    assert client.get("/api/time/time-entries", headers=user1).status_code == 200


def test_list_and_statistics_on_postgres(pg_app, client, user1, admin):
    seed(client, user1, count=3)
    client.post("/api/time/timer/start", json={"task_id": 9}, headers=user1)
    # идущая начата последней: первая при сортировке по убыванию
    assert items(client, user1)[0]["stopped_at"] is None
    body = client.get("/api/time/time-entries?limit=2&offset=1", headers=user1).json()
    assert (body["total"], len(body["items"])) == (4, 2)
    [row] = client.get("/api/time/statistics/users", headers=admin).json()
    assert row == {
        "user_id": 1,
        "entries_count": 3,
        "tasks_count": 2,
        "total_seconds": 180,
        "avg_seconds_per_task": 90,
    }
