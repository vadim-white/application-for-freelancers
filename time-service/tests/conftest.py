import os
import tempfile
from datetime import datetime, timedelta, timezone

# Окружение задаётся до импорта приложения: config и engine создаются при импорте
os.environ["SECRET_KEY"] = "test-secret"
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/time_test.db"

import pytest
from fastapi.testclient import TestClient
from jose import jwt

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
               secret=TEST_SECRET, exp=True):
    payload = {"sub": sub, "type": token_type}
    if role is not None:
        payload["role"] = role
    if exp:
        payload["exp"] = datetime.now(timezone.utc) + expires_in
    return jwt.encode(payload, secret, algorithm="HS256")


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def user1():
    return auth(make_token(sub="1"))


@pytest.fixture
def user2():
    return auth(make_token(sub="2"))


@pytest.fixture
def admin():
    return auth(make_token(sub="99", role="admin"))
