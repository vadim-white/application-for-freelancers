import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main
from app.core.config import settings
from app.main import app
from app.task_client import get_task_client
from tests.conftest import task_body


def start(client, headers, task_id=5):
    return client.post("/api/time/timer/start", json={"task_id": task_id}, headers=headers)


def entries(client, headers):
    return client.get("/api/time/time-entries", headers=headers).json()


def test_start_asks_task_service_with_user_token(client, user1, task_service):
    assert start(client, user1, task_id=5).status_code == 201
    [request] = task_service.calls
    assert request.method == "GET"
    assert request.url.path == "/api/tasks/tasks/5"
    assert request.headers["authorization"] == user1["Authorization"]


def test_admin_starts_on_any_task_for_own_user(client, admin):
    # task отдаёт admin любую задачу, запись — на admin
    assert start(client, admin).json()["entry"]["user_id"] == 99


def test_task_not_found_is_404(client, user1, task_service):
    task_service.handler = lambda request: httpx.Response(404, json={"detail": "Task not found"})
    r = start(client, user1)
    assert (r.status_code, r.json()) == (404, {"detail": "Task not found"})
    assert entries(client, user1) == []


@pytest.mark.parametrize(
    "body",
    [
        task_body(5, is_active=False),
        task_body(5, is_active=False, project_active=True),
        task_body(5, project_active=False),
    ],
    ids=["task", "task-in-project", "project"],
)
def test_archived_task_or_project_is_409(client, user1, task_service, body):
    task_service.handler = lambda request: httpx.Response(200, json=body)
    r = start(client, user1)
    assert (r.status_code, r.json()) == (409, {"detail": "Task is archived"})
    assert entries(client, user1) == []


def test_active_task_in_active_project_starts(client, user1, task_service):
    task_service.handler = lambda request: httpx.Response(200, json=task_body(5, True, True))
    assert start(client, user1).status_code == 201


def raise_(error):
    def handler(request):
        raise error("boom", request=request)

    return handler


@pytest.mark.parametrize(
    "handler",
    [
        raise_(httpx.ConnectTimeout),
        raise_(httpx.ReadTimeout),
        raise_(httpx.ConnectError),
        raise_(httpx.RemoteProtocolError),
        lambda request: httpx.Response(500),
        lambda request: httpx.Response(503, text="no healthy upstream"),
    ],
    ids=["connect-timeout", "read-timeout", "connect-error", "dropped", "500", "503"],
)
def test_task_service_down_is_503(client, user1, task_service, caplog, handler):
    task_service.handler = handler
    with caplog.at_level(logging.WARNING, logger="app.task_client"):
        r = start(client, user1)
    assert (r.status_code, r.json()) == (503, {"detail": "Task service unavailable"})
    # причина — только в логе
    assert "Task service" in caplog.text
    assert entries(client, user1) == []


@pytest.mark.parametrize("status", [401, 403])
def test_task_service_rejects_token_is_502(client, user1, task_service, status):
    task_service.handler = lambda request: httpx.Response(status)
    r = start(client, user1)
    assert (r.status_code, r.json()) == (502, {"detail": "Task service rejected request"})


def test_stop_and_current_work_without_task_service(client, user1, task_service):
    assert start(client, user1).status_code == 201
    task_service.handler = raise_(httpx.ConnectError)
    assert client.get("/api/time/timer", headers=user1).json()["entry"]["task_id"] == 5
    assert client.post("/api/time/timer/stop", headers=user1).json()["stopped"]["task_id"] == 5
    assert len(task_service.calls) == 1


def test_running_task_archived_keeps_running_until_stop(client, user1, task_service):
    entry = start(client, user1).json()["entry"]
    task_service.handler = lambda request: httpx.Response(200, json=task_body(5, is_active=False))
    # повторный старт той же задачи: проверка раньше идемпотентности
    assert start(client, user1).status_code == 409
    assert client.get("/api/time/timer", headers=user1).json()["entry"] == entry
    assert client.post("/api/time/timer/stop", headers=user1).json()["stopped"]["id"] == entry["id"]


def test_one_task_client_per_app(monkeypatch, user1):
    # настоящий клиент из lifespan и настоящая зависимость, только транспорт — мок
    created, seen = [], []
    real_client = httpx.AsyncClient

    def counting_client(*args, **kwargs):
        def handler(request):
            seen.append(str(request.url))
            return httpx.Response(200, json=task_body(5))

        created.append(real_client(*args, transport=httpx.MockTransport(handler), **kwargs))
        return created[-1]

    monkeypatch.setattr(main.httpx, "AsyncClient", counting_client)
    monkeypatch.setattr(settings, "TASK_SERVICE_URL", "http://ser-task:8002")
    app.dependency_overrides.pop(get_task_client)
    with TestClient(app) as c:
        for _ in range(2):
            assert start(c, user1).status_code in (200, 201)
    assert len(created) == 1
    assert created[0].timeout == httpx.Timeout(3.0, connect=2.0)
    assert seen == ["http://ser-task:8002/api/tasks/tasks/5"] * 2
    assert created[0].is_closed
