import os
import pathlib
import subprocess
import sys
from datetime import timedelta

import pytest

from app import api, crud, schemas
from app.db import SessionLocal

from .conftest import auth, make_token

SERVICE_ROOT = pathlib.Path(__file__).resolve().parent.parent

PROTECTED = [
    ("get", "/api/time/time-entries"),
    ("post", "/api/time/time-entries"),
    ("get", "/api/time/statistics/users"),
]


@pytest.mark.parametrize("method,path", PROTECTED)
def test_protected_without_token_401(client, method, path):
    r = client.request(method, path, json={})
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


def test_root_is_public(client):
    assert client.get("/").status_code == 200


@pytest.mark.parametrize("token", [
    make_token(expires_in=timedelta(minutes=-1)),
    make_token(exp=False),
    make_token(token_type="refresh"),
    make_token(secret="other-secret"),
    make_token(sub="abc"),
    make_token(role="superuser"),
    "not-a-jwt",
])
def test_invalid_tokens_401(client, token):
    assert client.get("/api/time/time-entries", headers=auth(token)).status_code == 401


def test_x_user_headers_without_token_401(client):
    r = client.get("/api/time/time-entries", headers={"X-User-Id": "1", "X-User-Role": "admin"})
    assert r.status_code == 401


def create(client, headers, **body):
    return client.post("/api/time/time-entries", json={"task_id": 1, "minutes": 10, **body}, headers=headers)


def test_user_id_taken_from_token_not_body(client, user1):
    r = create(client, user1, user_id=2)
    assert r.status_code == 200
    assert r.json()["user_id"] == 1


def test_create_validates_minutes(client, user1):
    assert create(client, user1, minutes=0).status_code == 422


def test_user_sees_only_own_entries(client, user1, user2):
    create(client, user1)
    create(client, user2)
    create(client, user2)
    r = client.get("/api/time/time-entries", headers=user1)
    assert [e["user_id"] for e in r.json()] == [1]
    assert len(client.get("/api/time/time-entries", headers=user2).json()) == 2


def test_user_cannot_query_other_user(client, user1, user2):
    create(client, user2)
    assert client.get("/api/time/time-entries?user_id=2", headers=user1).status_code == 403
    r = client.get("/api/time/time-entries?user_id=1", headers=user1)
    assert r.status_code == 200
    assert r.json() == []


def test_forged_role_header_does_not_grant_admin(client, user1, user2):
    create(client, user2)
    headers = {**user1, "X-User-Role": "admin"}
    assert client.get("/api/time/time-entries", headers=headers).json() == []


def test_task_filter_combined_with_own_entries(client, user1, user2):
    create(client, user1, task_id=5)
    create(client, user1, task_id=6)
    create(client, user2, task_id=5)
    r = client.get("/api/time/time-entries?task_id=5", headers=user1)
    assert [(e["task_id"], e["user_id"]) for e in r.json()] == [(5, 1)]


def test_admin_sees_all_and_can_filter(client, user1, user2, admin):
    create(client, user1)
    create(client, user2)
    assert len(client.get("/api/time/time-entries", headers=admin).json()) == 2
    r = client.get("/api/time/time-entries?user_id=2", headers=admin)
    assert [e["user_id"] for e in r.json()] == [2]


def test_statistics_admin_only(client, user1, admin):
    create(client, user1, minutes=10)
    create(client, user1, minutes=20)
    assert client.get("/api/time/statistics/users", headers=user1).status_code == 403
    r = client.get("/api/time/statistics/users", headers=admin)
    assert r.status_code == 200
    [row] = r.json()
    assert (row["user_id"], row["task_count"], row["avg_minutes"]) == (1, 2, 15)


def test_create_maps_crud_value_error_to_400(client, user1, monkeypatch):
    def fail(db, entry_in, user_id):
        raise ValueError("Invalid minutes value; must be > 0")

    monkeypatch.setattr(api.crud, "create_time_entry", fail)
    r = client.post("/api/time/time-entries", json={"task_id": 1, "minutes": 5}, headers=user1)
    assert r.status_code == 400
    assert r.json() == {"detail": "Invalid minutes value; must be > 0"}


@pytest.mark.parametrize("minutes", [0, -5, None])
def test_crud_rejects_non_positive_minutes(minutes):
    # схема не пропускает такие значения до crud: проверяем вторую линию защиты напрямую
    entry = schemas.TimeEntryCreate.model_construct(task_id=1, minutes=minutes)
    with SessionLocal() as db, pytest.raises(ValueError, match="must be > 0"):
        crud.create_time_entry(db, entry, user_id=1)


def test_statistics_db_error_returns_500(client, admin):
    class BrokenSession:
        def query(self, *args):
            raise RuntimeError("db down")

        def close(self):
            pass

    client.app.dependency_overrides[api.get_db] = BrokenSession
    try:
        r = client.get("/api/time/statistics/users", headers=admin)
    finally:
        client.app.dependency_overrides.pop(api.get_db)
    assert r.status_code == 500
    assert r.json() == {"detail": "Failed to get statistics"}


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
    r = subprocess.run([sys.executable, "-c", "import app.core.config"],
                       cwd=tmp_path, env=env, capture_output=True, text=True)
    assert r.returncode != 0
    assert "DATABASE_URL" in r.stderr
