import os
from datetime import UTC, datetime, timedelta

# Окружение задаётся до импорта приложения: config и CORS настраиваются при импорте
os.environ["SECRET_KEY"] = "test-secret"
os.environ["CORS_ORIGINS"] = "http://localhost:5173, http://app.example"

import httpx
import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app import proxy
from app.core.config import settings
from app.main import app

TEST_SECRET = "test-secret"


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY", TEST_SECRET)
    monkeypatch.setattr(settings, "ALGORITHM", "HS256")
    monkeypatch.setattr(settings, "AUTH_URL", "http://auth")
    monkeypatch.setattr(settings, "TASK_URL", "http://task")
    monkeypatch.setattr(settings, "TIME_URL", "http://time")


@pytest.fixture
def upstream(monkeypatch):
    """Подменяет сетевые вызовы gateway; хранит полученные upstream-запросы."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"ok": True})

    real_client = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(proxy.httpx, "AsyncClient", fake_client)
    return calls


@pytest.fixture
def client():
    return TestClient(app)


def make_token(sub="1", role="user", token_type="access", expires_in=timedelta(minutes=15),
               secret=TEST_SECRET, **extra):
    payload = {"sub": sub, "type": token_type, **extra}
    if role is not None:
        payload["role"] = role
    if expires_in is not None:
        payload["exp"] = datetime.now(UTC) + expires_in
    return jwt.encode(payload, secret, algorithm="HS256")


def bearer(token):
    return {"Authorization": f"Bearer {token}"}
