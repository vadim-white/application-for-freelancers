import threading
from collections import Counter
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import StatementError
from sqlalchemy.orm import sessionmaker

from app import api, crud, models, schemas
from app.core import security
from app.core.security import get_password_hash
from tests.conftest import PASSWORD, login

T0 = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
WINDOW = timedelta(seconds=900)
WRONG = "wrong-password"


@pytest.fixture
def clock(monkeypatch):
    """Подменяет «сейчас» сервиса: clock.at = datetime."""

    class Clock:
        at = T0

    monkeypatch.setattr(crud, "now", lambda: Clock.at)
    return Clock


@pytest.fixture
def bcrypt_calls(monkeypatch):
    """Хеши, с которыми bcrypt проверял пароль."""
    calls = []
    real_verify = security.password_hash.verify

    def spy(password, hashed):
        calls.append(hashed)
        return real_verify(password, hashed)

    monkeypatch.setattr(security.password_hash, "verify", spy)
    return calls


def fail(client, times, email="user@example.com"):
    return [login(client, email=email, password=WRONG).status_code for _ in range(times)]


def row(db, email="user@example.com"):
    db.expire_all()
    return db.get(models.LoginAttempts, email)


def test_sixth_attempt_is_429_with_retry_after(client, make_user, clock):
    make_user()
    assert fail(client, 5) == [401] * 5
    r = login(client, password=WRONG)
    assert r.status_code == 429
    assert r.json() == {"detail": "Too many login attempts"}
    assert r.headers["Retry-After"] == "900"


def test_locked_email_skips_password_check_even_if_correct(
    client, make_user, db, clock, bcrypt_calls
):
    make_user()
    fail(client, 5)
    assert len(bcrypt_calls) == 5
    clock.at = T0 + timedelta(seconds=60)
    assert login(client).status_code == 429
    assert login(client, password=WRONG).status_code == 429
    assert len(bcrypt_calls) == 5
    # попытки с 429 тоже считаются, но окно не сдвигают
    assert (row(db).attempts, row(db).window_start) == (7, T0)


def test_lock_ends_with_window(client, make_user, db, clock):
    make_user()
    fail(client, 6)
    clock.at = T0 + WINDOW
    assert login(client, password=WRONG).status_code == 401
    assert (row(db).attempts, row(db).window_start) == (1, T0 + WINDOW)
    assert login(client).status_code == 200


def test_retry_after_counts_down_to_window_end(client, make_user, clock):
    make_user()
    fail(client, 5)
    clock.at = T0 + timedelta(seconds=100.5)
    assert login(client).headers["Retry-After"] == "800"
    clock.at = T0 + WINDOW - timedelta(seconds=0.2)
    assert login(client).headers["Retry-After"] == "1"


def test_correct_password_resets_counter(client, make_user, db, clock):
    make_user()
    assert fail(client, 4) == [401] * 4
    assert login(client).status_code == 200
    assert row(db) is None
    assert fail(client, 5) == [401] * 5
    assert login(client).status_code == 429


def test_inactive_user_with_correct_password_resets_counter(client, make_user, db, clock):
    make_user(is_active=False)
    fail(client, 4)
    assert login(client).status_code == 403
    assert row(db) is None


def test_unknown_email_is_counted_the_same(client, db, clock, bcrypt_calls):
    email = "nobody@example.com"
    assert fail(client, 5, email=email) == [401] * 5
    assert bcrypt_calls == [security.DUMMY_HASH] * 5
    r = login(client, email=email, password=WRONG)
    assert (r.status_code, r.headers["Retry-After"]) == (429, "900")
    assert len(bcrypt_calls) == 5
    assert row(db, email).attempts == 6


def test_email_case_shares_one_counter(client, make_user, db, clock):
    make_user()
    assert fail(client, 3, email="User@Example.com") == [401] * 3
    assert fail(client, 2) == [401] * 2
    assert login(client, email="USER@EXAMPLE.COM").status_code == 429
    assert row(db).attempts == 6


def test_counter_is_per_email(client, make_user, clock):
    make_user()
    make_user(email="other@example.com")
    fail(client, 6)
    assert login(client, email="other@example.com").status_code == 200


def test_success_removes_expired_rows_and_keeps_live(client, make_user, db, clock):
    make_user()
    live = T0 - WINDOW + timedelta(seconds=1)
    db.add_all(
        [
            models.LoginAttempts(email="old@example.com", attempts=6, window_start=T0 - WINDOW),
            models.LoginAttempts(email="live@example.com", attempts=6, window_start=live),
        ]
    )
    db.commit()
    fail(client, 1)
    assert login(client).status_code == 200
    db.expire_all()
    assert db.scalars(select(models.LoginAttempts.email)).all() == ["live@example.com"]


def test_naive_time_rejected(db):
    naive = datetime(2026, 10, 26, 12, 0)
    db.add(models.LoginAttempts(email="x@example.com", attempts=1, window_start=naive))
    with pytest.raises(StatementError, match="timezone-aware"):
        db.commit()


def test_password_over_72_bytes_not_counted(client, db, clock):
    r = client.post("/api/auth/login", json={"email": "user@example.com", "password": "я" * 37})
    assert r.status_code == 422
    assert row(db) is None


def test_refresh_works_while_login_locked(client, make_user, clock):
    make_user()
    refresh_token = login(client).json()["refresh_token"]
    fail(client, 6)
    r = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert r.status_code == 200


def test_login_limit_on_postgres(pg_app, client, clock):
    Session = sessionmaker(autoflush=False, bind=pg_app.engine)
    with Session() as db:
        db.add(models.User(email="pg@example.com", hashed_password=get_password_hash(PASSWORD)))
        db.commit()
        email = "pg@example.com"
        assert fail(client, 5, email=email) == [401] * 5
        r = login(client, email=email, password=WRONG)
        assert (r.status_code, r.headers["Retry-After"]) == (429, "900")
        assert (row(db, email).attempts, row(db, email).window_start) == (6, T0)

        clock.at = T0 + WINDOW
        assert fail(client, 1, email=email) == [401]
        assert (row(db, email).attempts, row(db, email).window_start) == (1, T0 + WINDOW)
        assert login(client, email=email).status_code == 200
        assert row(db, email) is None


def test_parallel_failed_logins_on_postgres_check_five_passwords(pg_app, monkeypatch):
    """8 одновременных неверных входов через разные реплики: bcrypt проверяет ровно пять."""
    Session = sessionmaker(autoflush=False, bind=pg_app.engine)
    email = "race@example.com"
    with Session() as db:
        db.add(models.User(email=email, hashed_password=security.DUMMY_HASH))
        db.commit()

    # все запросы подходят к счётчику одновременно, каждый со своим соединением
    barrier = threading.Barrier(8)
    real_count = crud.count_login_attempt

    def count_together(db, email, now):
        barrier.wait(5)
        return real_count(db, email, now)

    monkeypatch.setattr(crud, "count_login_attempt", count_together)
    results = []

    def attempt():
        with Session() as db:
            try:
                api.login(schemas.UserAuth(email=email, password=WRONG), db)
                results.append(200)
            except HTTPException as exc:
                results.append(exc.status_code)
            except Exception:
                results.append(500)

    threads = [threading.Thread(target=attempt) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(20)

    assert Counter(results) == {401: 5, 429: 3}
    with Session() as db:
        assert row(db, email).attempts == 8
