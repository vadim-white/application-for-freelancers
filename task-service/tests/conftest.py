import os
import tempfile
from datetime import datetime, timedelta, timezone

# Окружение задаётся до импорта приложения: config и engine создаются при импорте
os.environ["SECRET_KEY"] = "test-secret"
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/task_test.db"
os.environ["TIME_SERVICE_URL"] = "http://time"

import httpx
import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app import api
from app.db import Base, engine
from app.main import app

TEST_SECRET = "test-secret"


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client():
    return TestClient(app)


def make_token(sub="1", role="user", token_type="access", expires_in=timedelta(minutes=5),
               secret=TEST_SECRET, exp=True, **extra):
    payload = {"sub": sub, "type": token_type, **extra}
    if role is not None:
        payload["role"] = role
    if exp:
        payload["exp"] = datetime.now(timezone.utc) + expires_in
    return jwt.encode(payload, secret, algorithm="HS256")


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def user_headers():
    return auth(make_token(sub="1", role="user"))


@pytest.fixture
def other_headers():
    """Второй пользователь: на его объекты user_headers должен получать 404."""
    return auth(make_token(sub="2", role="user"))


@pytest.fixture
def admin_headers():
    return auth(make_token(sub="99", role="admin"))


@pytest.fixture
def time_service(monkeypatch):
    """Подменяет вызовы task -> time; хранит запросы, ответ задаётся через state."""
    state = {"calls": [], "response": httpx.Response(200, json=[{"user_id": 1, "task_count": 2}])}

    def handler(request: httpx.Request) -> httpx.Response:
        state["calls"].append(request)
        if isinstance(state["response"], Exception):
            raise state["response"]
        return state["response"]

    real_client = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(api.httpx, "AsyncClient", fake_client)
    return state
