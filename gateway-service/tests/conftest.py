import inspect
import os
from datetime import UTC, datetime, timedelta

# Окружение задаётся до импорта приложения: config и CORS настраиваются при импорте
os.environ["SECRET_KEY"] = "test-secret-key-at-least-32-bytes-long"
os.environ["CORS_ORIGINS"] = "http://localhost:5173, http://app.example"

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.proxy import get_http_client

TEST_SECRET = "test-secret-key-at-least-32-bytes-long"


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY", TEST_SECRET)
    monkeypatch.setattr(settings, "ALGORITHM", "HS256")
    monkeypatch.setattr(settings, "AUTH_URL", "http://auth")
    monkeypatch.setattr(settings, "TASK_URL", "http://task")
    monkeypatch.setattr(settings, "TIME_URL", "http://time")


def as_network_stream(handler):
    """httpx.Response(content=bytes) создаётся уже прочитанным; настоящий транспорт отдаёт тело
    потоком, и прокси читает его через aiter_raw — поэтому тело оборачивается в поток."""

    async def wrapped(request: httpx.Request) -> httpx.Response:
        response = handler(request)
        if inspect.isawaitable(response):
            response = await response
        if not response.is_stream_consumed:
            return response

        # stream — байты как переданы в тест, до распаковки content-encoding
        raw = b"".join(response.stream)

        async def body():
            yield raw

        return httpx.Response(response.status_code, headers=response.headers, content=body())

    return wrapped


@pytest.fixture
def mock_upstream():
    """Подменяет общий клиент gateway клиентом на MockTransport с заданным обработчиком."""

    def install(handler):
        client = httpx.AsyncClient(transport=httpx.MockTransport(as_network_stream(handler)))
        app.dependency_overrides[get_http_client] = lambda: client

    yield install
    app.dependency_overrides.pop(get_http_client, None)


@pytest.fixture
def upstream(mock_upstream):
    """Сервисы отвечают 200; хранит полученные upstream-запросы."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"ok": True})

    mock_upstream(handler)
    return calls


@pytest.fixture
def client():
    return TestClient(app)


def make_token(
    sub="1",
    role="user",
    token_type="access",
    expires_in=timedelta(minutes=15),
    secret=TEST_SECRET,
    **extra,
):
    payload = {"sub": sub, "type": token_type, **extra}
    if role is not None:
        payload["role"] = role
    if expires_in is not None:
        payload["exp"] = datetime.now(UTC) + expires_in
    return jwt.encode(payload, secret, algorithm="HS256")


def bearer(token):
    return {"Authorization": f"Bearer {token}"}
