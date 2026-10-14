import os
import pathlib
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app import models
from app.core.config import settings
from app.main import app
from tests.conftest import PASSWORD, login

SERVICE_ROOT = pathlib.Path(__file__).resolve().parent.parent


def claims(token):
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def refresh(client, token):
    return client.post("/api/auth/refresh", json={"refresh_token": token})


def make_token(sub, token_type, expires_in=timedelta(minutes=5), **extra):
    payload = {"sub": sub, "type": token_type, **extra}
    if expires_in is not None:
        payload["exp"] = datetime.now(timezone.utc) + expires_in
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


# --- register ---

def test_register_creates_user_with_role_user(client):
    r = client.post("/api/auth/register", json={"email": "new@example.com", "password": PASSWORD})
    assert r.status_code == 201
    assert r.json()["role"] == "user"
    assert login(client, "new@example.com").status_code == 200


# --- login ---

@pytest.mark.parametrize("role", [models.UserRole.user, models.UserRole.admin])
def test_login_returns_tokens_with_role(client, make_user, role):
    user = make_user(role=role)
    r = login(client)
    assert r.status_code == 200
    access = claims(r.json()["access_token"])
    assert access["sub"] == str(user.id)
    assert access["type"] == "access"
    assert access["role"] == role.value
    assert "exp" in access
    assert claims(r.json()["refresh_token"])["type"] == "refresh"


def test_login_wrong_password(client, make_user):
    make_user()
    assert login(client, password="wrong-password").status_code == 401


def test_login_unknown_email(client):
    assert login(client, email="nobody@example.com").status_code == 401


def test_login_inactive_user(client, make_user):
    make_user(is_active=False)
    r = login(client)
    assert r.status_code == 403
    assert "access_token" not in r.json()


# --- refresh ---

def test_refresh_keeps_role(client, make_user):
    make_user(role=models.UserRole.admin)
    rt = login(client).json()["refresh_token"]
    r = refresh(client, rt)
    assert r.status_code == 200
    access = claims(r.json()["access_token"])
    assert access["role"] == "admin"
    assert access["type"] == "access"


def test_refresh_uses_current_role_from_db(client, make_user, db):
    user = make_user(role=models.UserRole.admin)
    rt = login(client).json()["refresh_token"]
    user.role = models.UserRole.user
    db.commit()
    assert claims(refresh(client, rt).json()["access_token"])["role"] == "user"


def test_refresh_inactive_user(client, make_user, db):
    user = make_user()
    rt = login(client).json()["refresh_token"]
    user.is_active = False
    db.commit()
    assert refresh(client, rt).status_code == 401


def test_refresh_deleted_user(client, make_user, db):
    user = make_user()
    rt = login(client).json()["refresh_token"]
    db.delete(user)
    db.commit()
    assert refresh(client, rt).status_code == 401


def test_refresh_rejects_access_token(client, make_user):
    make_user()
    at = login(client).json()["access_token"]
    assert refresh(client, at).status_code == 401


@pytest.mark.parametrize("token", [
    "not-a-jwt",
    make_token("1", "refresh", expires_in=timedelta(seconds=-10)),
    make_token("1", "refresh", expires_in=None),
    make_token(None, "refresh"),
    make_token("abc", "refresh"),
], ids=["garbage", "expired", "no-exp", "no-sub", "bad-sub"])
def test_refresh_invalid_tokens(client, make_user, token):
    make_user()
    assert refresh(client, token).status_code == 401


# --- /me ---

def test_me(client, make_user):
    make_user(role=models.UserRole.admin)
    at = login(client).json()["access_token"]
    r = client.get("/api/auth/me", headers=bearer(at))
    assert r.status_code == 200
    assert r.json()["email"] == "user@example.com"
    assert r.json()["role"] == "admin"


def test_me_after_refresh(client, make_user):
    make_user()
    rt = login(client).json()["refresh_token"]
    at = refresh(client, rt).json()["access_token"]
    assert client.get("/api/auth/me", headers=bearer(at)).status_code == 200


def test_me_rejects_refresh_token(client, make_user):
    make_user()
    rt = login(client).json()["refresh_token"]
    assert client.get("/api/auth/me", headers=bearer(rt)).status_code == 401


def test_me_without_token(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_expired_token(client, make_user):
    user = make_user()
    token = make_token(str(user.id), "access", expires_in=timedelta(seconds=-10), role="user")
    r = client.get("/api/auth/me", headers=bearer(token))
    assert r.status_code == 401
    assert "Signature" not in r.text  # текст исключения не утекает


@pytest.mark.parametrize("is_active, delete", [(False, False), (True, True)], ids=["inactive", "deleted"])
def test_me_inactive_or_deleted_user(client, make_user, db, is_active, delete):
    user = make_user()
    at = login(client).json()["access_token"]
    if delete:
        db.delete(user)
    else:
        user.is_active = is_active
    db.commit()
    assert client.get("/api/auth/me", headers=bearer(at)).status_code == 401


# --- seed тестовых пользователей ---

def test_no_seed_by_default(db):
    with TestClient(app):
        pass
    assert db.query(models.User).count() == 0


def test_seed_when_enabled(db, monkeypatch):
    monkeypatch.setattr(settings, "SEED_TEST_USERS", True)
    with TestClient(app) as client:
        r = login(client, email="admin@example.com")
    assert r.status_code == 200
    assert claims(r.json()["access_token"])["role"] == "admin"
    assert db.query(models.User).count() == 3


# --- SECRET_KEY обязателен ---

@pytest.mark.parametrize("secret", [None, ""], ids=["missing", "empty"])
def test_settings_require_secret_key(tmp_path, secret):
    env = {k: v for k, v in os.environ.items() if k != "SECRET_KEY"}
    if secret is not None:
        env["SECRET_KEY"] = secret
    env["PYTHONPATH"] = str(SERVICE_ROOT)
    # cwd без .env, иначе ключ подтянется оттуда
    r = subprocess.run([sys.executable, "-c", "import app.core.config"],
                       cwd=tmp_path, env=env, capture_output=True, text=True)
    assert r.returncode != 0
    assert "SECRET_KEY" in r.stderr


def test_settings_accept_secret_key_from_env(tmp_path):
    env = {**os.environ, "SECRET_KEY": "from-env", "PYTHONPATH": str(SERVICE_ROOT)}
    r = subprocess.run([sys.executable, "-c", "from app.core.config import settings; print(settings.SECRET_KEY)"],
                       cwd=tmp_path, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "from-env"


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
