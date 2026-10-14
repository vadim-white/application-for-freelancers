import os
import pathlib
import subprocess
import sys
from datetime import timedelta

import httpx
import pytest

from .conftest import auth, make_token

SERVICE_ROOT = pathlib.Path(__file__).resolve().parent.parent

PROTECTED = [
    ("get", "/api/tasks/tasks"),
    ("post", "/api/tasks/tasks"),
    ("get", "/api/tasks/tasks/1"),
    ("put", "/api/tasks/tasks/1"),
    ("delete", "/api/tasks/tasks/1"),
    ("post", "/api/tasks/tasks/1/status"),
    ("get", "/api/tasks/projects"),
    ("post", "/api/tasks/projects"),
    ("get", "/api/tasks/projects/1"),
    ("put", "/api/tasks/projects/1"),
    ("delete", "/api/tasks/projects/1"),
    ("get", "/api/tasks/statistics/users"),
]


@pytest.mark.parametrize("method,path", PROTECTED)
def test_protected_without_token_401(client, method, path):
    r = client.request(method, path, json={})
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


def test_root_is_public(client):
    assert client.get("/").status_code == 200


@pytest.mark.parametrize("token", [
    make_token(expires_in=timedelta(minutes=-1)),          # просрочен
    make_token(exp=False),                                 # без exp
    make_token(token_type="refresh"),                      # refresh вместо access
    make_token(secret="other-secret"),                     # чужая подпись
    make_token(sub="abc"),                                 # sub не число
    make_token(role="superuser"),                          # неизвестная роль
    "not-a-jwt",
])
def test_invalid_tokens_401(client, token):
    assert client.get("/api/tasks/tasks", headers=auth(token)).status_code == 401


def test_non_bearer_scheme_401(client):
    r = client.get("/api/tasks/tasks", headers={"Authorization": f"Basic {make_token()}"})
    assert r.status_code == 401


def test_x_user_headers_without_token_401(client):
    r = client.get("/api/tasks/tasks", headers={"X-User-Id": "99", "X-User-Role": "admin"})
    assert r.status_code == 401


def test_user_can_work_with_tasks(client, user_headers):
    r = client.post("/api/tasks/tasks", json={"title": "t1"}, headers=user_headers)
    assert r.status_code == 201
    task_id = r.json()["id"]
    assert client.get("/api/tasks/tasks", headers=user_headers).json()[0]["id"] == task_id
    r = client.post(f"/api/tasks/tasks/{task_id}/status", json={"status": "done"}, headers=user_headers)
    assert r.json()["status"] == "done"


def test_token_without_role_is_user(client):
    headers = auth(make_token(role=None))
    assert client.get("/api/tasks/tasks", headers=headers).status_code == 200
    assert client.post("/api/tasks/projects", json={"name": "p"}, headers=headers).status_code == 403


def test_project_mutations_admin_only(client, user_headers, admin_headers):
    assert client.post("/api/tasks/projects", json={"name": "p"}, headers=user_headers).status_code == 403
    r = client.post("/api/tasks/projects", json={"name": "p"}, headers=admin_headers)
    assert r.status_code == 201
    pid = r.json()["id"]
    assert client.put(f"/api/tasks/projects/{pid}", json={"name": "x"}, headers=user_headers).status_code == 403
    assert client.delete(f"/api/tasks/projects/{pid}", headers=user_headers).status_code == 403
    assert client.put(f"/api/tasks/projects/{pid}", json={"name": "x"}, headers=admin_headers).status_code == 200
    assert client.delete(f"/api/tasks/projects/{pid}", headers=admin_headers).status_code == 204


def test_forged_role_header_does_not_grant_admin(client, user_headers):
    headers = {**user_headers, "X-User-Role": "admin", "X-User-Id": "99"}
    assert client.post("/api/tasks/projects", json={"name": "p"}, headers=headers).status_code == 403


def test_statistics_user_403(client, user_headers, time_service):
    assert client.get("/api/tasks/statistics/users", headers=user_headers).status_code == 403
    assert time_service["calls"] == []


def test_statistics_admin_forwards_authorization(client, admin_headers, time_service):
    r = client.get("/api/tasks/statistics/users", headers=admin_headers)
    assert r.status_code == 200
    assert r.json() == [{"user_id": 1, "task_count": 2}]
    [call] = time_service["calls"]
    assert str(call.url) == "http://time/api/time/statistics/users"
    assert call.headers["authorization"] == admin_headers["Authorization"]


def test_statistics_time_error_502(client, admin_headers, time_service):
    time_service["response"] = httpx.Response(401, json={"detail": "Invalid token"})
    r = client.get("/api/tasks/statistics/users", headers=admin_headers)
    assert r.status_code == 502


def test_statistics_time_unreachable_502_without_details(client, admin_headers, time_service):
    time_service["response"] = httpx.ConnectError("secret internal host")
    r = client.get("/api/tasks/statistics/users", headers=admin_headers)
    assert r.status_code == 502
    assert "secret" not in r.text


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
