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
    assert client.get("/api/tasks/statistics/users", headers=headers).status_code == 403


def test_user_can_manage_own_project(client, user_headers):
    r = client.post("/api/tasks/projects", json={"name": "p"}, headers=user_headers)
    assert r.status_code == 201
    pid = r.json()["id"]
    assert r.json()["owner_id"] == 1
    assert client.put(f"/api/tasks/projects/{pid}", json={"name": "x"}, headers=user_headers).status_code == 200
    assert client.delete(f"/api/tasks/projects/{pid}", headers=user_headers).status_code == 204


def test_forged_role_header_does_not_grant_admin(client, user_headers, other_headers):
    pid = client.post("/api/tasks/projects", json={"name": "p"}, headers=other_headers).json()["id"]
    headers = {**user_headers, "X-User-Role": "admin", "X-User-Id": "2"}
    assert client.get(f"/api/tasks/projects/{pid}", headers=headers).status_code == 404
    assert client.get("/api/tasks/projects", headers=headers).json() == []
    assert client.get("/api/tasks/statistics/users", headers=headers).status_code == 403


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


# --- Владелец проектов и задач (owner_id из токена) ---

def test_project_owner_from_token(client, admin_headers):
    r = client.post("/api/tasks/projects", json={"name": "p"}, headers=admin_headers)
    assert r.status_code == 201
    pid = r.json()["id"]
    assert r.json()["owner_id"] == 99
    assert client.get(f"/api/tasks/projects/{pid}", headers=admin_headers).json()["owner_id"] == 99
    assert client.get("/api/tasks/projects", headers=admin_headers).json()[0]["owner_id"] == 99


def test_task_without_project_owner_from_token(client, user_headers):
    r = client.post("/api/tasks/tasks", json={"title": "t"}, headers=user_headers)
    assert r.status_code == 201
    tid = r.json()["id"]
    assert r.json()["project_id"] is None
    assert r.json()["owner_id"] == 1
    assert client.get(f"/api/tasks/tasks/{tid}", headers=user_headers).json()["owner_id"] == 1
    assert client.get("/api/tasks/tasks", headers=user_headers).json()[0]["owner_id"] == 1


def test_owner_id_in_body_ignored(client, user_headers, admin_headers):
    r = client.post("/api/tasks/projects", json={"name": "p", "owner_id": 5}, headers=admin_headers)
    assert r.status_code == 201
    pid = r.json()["id"]
    assert r.json()["owner_id"] == 99
    r = client.put(f"/api/tasks/projects/{pid}", json={"name": "x", "owner_id": 5}, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["owner_id"] == 99

    r = client.post("/api/tasks/tasks", json={"title": "t", "owner_id": 5}, headers=user_headers)
    assert r.status_code == 201
    tid = r.json()["id"]
    assert r.json()["owner_id"] == 1
    r = client.put(f"/api/tasks/tasks/{tid}", json={"title": "x", "owner_id": 5}, headers=user_headers)
    assert r.status_code == 200
    assert r.json()["owner_id"] == 1


def test_admin_task_in_foreign_project_gets_project_owner(client, user_headers, admin_headers):
    pid = client.post("/api/tasks/projects", json={"name": "чужой"}, headers=user_headers).json()["id"]
    r = client.post("/api/tasks/tasks", json={"title": "t", "project_id": pid}, headers=admin_headers)
    assert r.status_code == 201
    assert r.json()["owner_id"] == 1
    assert r.json()["project"]["owner_id"] == 1
    # задача видна владельцу проекта
    assert [t["id"] for t in client.get("/api/tasks/tasks", headers=user_headers).json()] == [r.json()["id"]]


# --- Доступ «только свои» (1.2.6) ---

def _project(client, headers, name="p"):
    r = client.post("/api/tasks/projects", json={"name": name}, headers=headers)
    assert r.status_code == 201
    return r.json()["id"]


def _task(client, headers, title="t", **fields):
    r = client.post("/api/tasks/tasks", json={"title": title, **fields}, headers=headers)
    assert r.status_code == 201
    return r.json()["id"]


def test_projects_list_only_own_admin_sees_all(client, user_headers, other_headers, admin_headers):
    p1 = _project(client, user_headers, "u1")
    p2 = _project(client, other_headers, "u2")
    pa = _project(client, admin_headers, "adm")
    assert [p["id"] for p in client.get("/api/tasks/projects", headers=user_headers).json()] == [p1]
    assert [p["id"] for p in client.get("/api/tasks/projects", headers=other_headers).json()] == [p2]
    assert {p["id"] for p in client.get("/api/tasks/projects", headers=admin_headers).json()} == {p1, p2, pa}


def test_foreign_project_404(client, user_headers, other_headers):
    pid = _project(client, other_headers, "чужой")
    assert client.get(f"/api/tasks/projects/{pid}", headers=user_headers).status_code == 404
    assert client.put(f"/api/tasks/projects/{pid}", json={"name": "x"}, headers=user_headers).status_code == 404
    assert client.delete(f"/api/tasks/projects/{pid}", headers=user_headers).status_code == 404
    # ответ на чужой такой же, как на несуществующий
    missing = client.get("/api/tasks/projects/99999", headers=user_headers)
    assert missing.status_code == 404
    assert client.get(f"/api/tasks/projects/{pid}", headers=user_headers).json() == missing.json()
    # проект не изменился и не удалён
    assert client.get(f"/api/tasks/projects/{pid}", headers=other_headers).json()["name"] == "чужой"


def test_admin_reads_updates_deletes_foreign_project(client, user_headers, admin_headers):
    pid = _project(client, user_headers)
    tid = _task(client, user_headers, project_id=pid)
    assert client.get(f"/api/tasks/projects/{pid}", headers=admin_headers).status_code == 200
    r = client.put(f"/api/tasks/projects/{pid}", json={"name": "x"}, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["owner_id"] == 1  # владелец не меняется
    assert client.delete(f"/api/tasks/projects/{pid}", headers=admin_headers).status_code == 204
    assert client.get(f"/api/tasks/projects/{pid}", headers=user_headers).status_code == 404
    assert client.get(f"/api/tasks/tasks/{tid}", headers=user_headers).status_code == 404  # каскад


def test_tasks_list_only_own_and_filters_inside_own(client, user_headers, other_headers, admin_headers):
    p1 = _project(client, user_headers)
    p2 = _project(client, other_headers)
    t1 = _task(client, user_headers, project_id=p1, status="done")
    t1_free = _task(client, user_headers)
    t2 = _task(client, other_headers, project_id=p2, status="done")
    t2_free = _task(client, other_headers)

    def ids(headers, **params):
        r = client.get("/api/tasks/tasks", params=params, headers=headers)
        assert r.status_code == 200
        return {t["id"] for t in r.json()}

    assert ids(user_headers) == {t1, t1_free}
    assert ids(other_headers) == {t2, t2_free}
    assert ids(admin_headers) == {t1, t1_free, t2, t2_free}
    # фильтры не выводят за пределы своих
    assert ids(user_headers, project_id=p2) == set()
    assert ids(user_headers, project_id=p1) == {t1}
    assert ids(user_headers, status="done") == {t1}
    assert ids(admin_headers, status="done") == {t1, t2}
    assert ids(admin_headers, project_id=p2) == {t2}


def test_foreign_task_404(client, user_headers, other_headers):
    tid = _task(client, other_headers, "чужая")
    assert client.get(f"/api/tasks/tasks/{tid}", headers=user_headers).status_code == 404
    assert client.put(f"/api/tasks/tasks/{tid}", json={"title": "x"}, headers=user_headers).status_code == 404
    assert client.post(f"/api/tasks/tasks/{tid}/status", json={"status": "done"},
                       headers=user_headers).status_code == 404
    assert client.delete(f"/api/tasks/tasks/{tid}", headers=user_headers).status_code == 404
    r = client.get(f"/api/tasks/tasks/{tid}", headers=other_headers).json()
    assert (r["title"], r["status"]) == ("чужая", "todo")


def test_admin_reads_updates_deletes_foreign_task(client, user_headers, admin_headers):
    tid = _task(client, user_headers)
    assert client.get(f"/api/tasks/tasks/{tid}", headers=admin_headers).status_code == 200
    r = client.put(f"/api/tasks/tasks/{tid}", json={"title": "x"}, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["owner_id"] == 1
    r = client.post(f"/api/tasks/tasks/{tid}/status", json={"status": "done"}, headers=admin_headers)
    assert r.json()["status"] == "done"
    assert client.delete(f"/api/tasks/tasks/{tid}", headers=admin_headers).status_code == 204


def test_user_task_in_foreign_project_404(client, user_headers, other_headers):
    pid = _project(client, other_headers)
    r = client.post("/api/tasks/tasks", json={"title": "t", "project_id": pid}, headers=user_headers)
    assert r.status_code == 404
    assert client.get("/api/tasks/tasks", headers=other_headers).json() == []


@pytest.mark.parametrize("project_id", [0, 99999])
def test_task_in_missing_project_404(client, user_headers, admin_headers, project_id):
    # project_id=0 раньше проходил без проверки (if project_id:), на PostgreSQL — 500
    for headers in (user_headers, admin_headers):
        r = client.post("/api/tasks/tasks", json={"title": "t", "project_id": project_id}, headers=headers)
        assert r.status_code == 404
    assert client.get("/api/tasks/tasks", headers=admin_headers).json() == []


def test_move_task_to_own_project(client, user_headers):
    p1 = _project(client, user_headers, "a")
    p2 = _project(client, user_headers, "b")
    tid = _task(client, user_headers, project_id=p1)
    r = client.put(f"/api/tasks/tasks/{tid}", json={"project_id": p2}, headers=user_headers)
    assert r.status_code == 200
    assert r.json()["project_id"] == p2


@pytest.mark.parametrize("target", ["foreign", 0, 99999])
def test_user_move_task_to_foreign_or_missing_project_404(client, user_headers, other_headers, target):
    p1 = _project(client, user_headers)
    if target == "foreign":
        target = _project(client, other_headers)
    tid = _task(client, user_headers, project_id=p1)
    r = client.put(f"/api/tasks/tasks/{tid}", json={"project_id": target, "title": "x"}, headers=user_headers)
    assert r.status_code == 404
    t = client.get(f"/api/tasks/tasks/{tid}", headers=user_headers).json()
    assert (t["project_id"], t["title"]) == (p1, "t")


def test_admin_move_task(client, user_headers, other_headers, admin_headers):
    p1 = _project(client, user_headers, "a")
    p1b = _project(client, user_headers, "b")
    p2 = _project(client, other_headers)
    tid = _task(client, user_headers, project_id=p1)
    # в проект другого владельца — 400:
    # иначе задача пользователя 1 окажется в проекте пользователя 2
    r = client.put(f"/api/tasks/tasks/{tid}", json={"project_id": p2}, headers=admin_headers)
    assert r.status_code == 400
    for missing in (0, 99999):
        r = client.put(f"/api/tasks/tasks/{tid}", json={"project_id": missing}, headers=admin_headers)
        assert r.status_code == 404
    assert client.get(f"/api/tasks/tasks/{tid}", headers=user_headers).json()["project_id"] == p1
    # в другой проект владельца задачи — можно
    r = client.put(f"/api/tasks/tasks/{tid}", json={"project_id": p1b}, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["project_id"] == p1b
    assert r.json()["owner_id"] == 1
