import os
import tempfile

# Окружение задаётся до импорта приложения: config и engine создаются при импорте
os.environ["SECRET_KEY"] = "test-secret"
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/auth_test.db"
os.environ["SEED_TEST_USERS"] = "false"

import pytest
from fastapi.testclient import TestClient

from app import models
from app.core.security import get_password_hash
from app.db import Base, SessionLocal, engine
from app.main import app

PASSWORD = "password123"


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def make_user(db):
    def _make(email="user@example.com", role=models.UserRole.user, is_active=True):
        user = models.User(
            email=email,
            hashed_password=get_password_hash(PASSWORD),
            role=role,
            is_active=is_active,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    return _make


def login(client, email="user@example.com", password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})
