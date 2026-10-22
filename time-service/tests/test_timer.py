import threading
import time
from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app import crud, schemas
from app.db import SessionLocal, engine
from app.models import TimeEntry, UTCDateTime

T0 = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/time/timer"),
        ("post", "/api/time/timer/start"),
        ("post", "/api/time/timer/stop"),
    ],
)
def test_timer_without_token_401(client, method, path):
    assert client.request(method, path, json={"task_id": 1}).status_code == 401


@pytest.fixture
def clock(monkeypatch):
    """Подменяет «сейчас» сервиса: clock.at = datetime."""

    class Clock:
        at = T0

    monkeypatch.setattr(crud, "now", lambda: Clock.at)
    return Clock


def start(client, headers, task_id=1, **body):
    return client.post("/api/time/timer/start", json={"task_id": task_id, **body}, headers=headers)


def stop(client, headers):
    return client.post("/api/time/timer/stop", headers=headers)


def current(client, headers):
    return client.get("/api/time/timer", headers=headers).json()


def parse(value):
    return datetime.fromisoformat(value)


def test_no_timer(client, user1):
    r = client.get("/api/time/timer", headers=user1)
    assert r.status_code == 200
    body = r.json()
    assert body["entry"] is None
    assert parse(body["server_time"]).utcoffset() == timedelta(0)


def test_start_get_stop(client, user1, clock):
    r = start(client, user1, task_id=5, description="note")
    assert r.status_code == 201
    body = r.json()
    entry = body["entry"]
    assert body["stopped"] is None
    assert (entry["task_id"], entry["user_id"], entry["description"]) == (5, 1, "note")
    assert parse(entry["started_at"]) == T0
    assert (entry["stopped_at"], entry["duration_seconds"]) == (None, None)
    # идущая запись читается и старыми подами: у них minutes > 0 обязателен
    assert entry["minutes"] == 1
    assert current(client, user1)["entry"] == entry

    clock.at = T0 + timedelta(minutes=3)
    r = stop(client, user1)
    assert r.status_code == 200
    stopped = r.json()["stopped"]
    assert stopped["id"] == entry["id"]
    assert parse(stopped["stopped_at"]) == clock.at
    assert (stopped["duration_seconds"], stopped["minutes"]) == (180, 3)
    assert current(client, user1)["entry"] is None


def test_stop_without_timer_returns_null(client, user1, clock):
    assert stop(client, user1).json()["stopped"] is None
    start(client, user1)
    assert stop(client, user1).json()["stopped"] is not None
    r = stop(client, user1)
    assert r.status_code == 200
    assert r.json()["stopped"] is None


def test_start_same_task_is_idempotent(client, user1, clock):
    first = start(client, user1, task_id=5).json()["entry"]
    clock.at = T0 + timedelta(minutes=1)
    r = start(client, user1, task_id=5)
    assert r.status_code == 200
    assert r.json()["entry"] == first
    assert r.json()["stopped"] is None
    assert client.get("/api/time/time-entries", headers=user1).json()["total"] == 1


def test_start_other_task_stops_running(client, user1, clock):
    first = start(client, user1, task_id=5).json()["entry"]
    clock.at = T0 + timedelta(seconds=90)
    r = start(client, user1, task_id=6)
    assert r.status_code == 201
    body = r.json()
    assert body["stopped"]["id"] == first["id"]
    assert (body["stopped"]["duration_seconds"], body["stopped"]["minutes"]) == (90, 2)
    assert body["stopped"]["stopped_at"] == body["entry"]["started_at"]
    assert body["entry"]["task_id"] == 6
    assert current(client, user1)["entry"]["id"] == body["entry"]["id"]


@pytest.mark.parametrize(
    "elapsed,seconds,minutes",
    [(0, 0, 1), (59.9, 59, 1), (60, 60, 1), (61.5, 61, 2)],
)
def test_duration_is_floored_and_minutes_rounded_up(
    client, user1, clock, elapsed, seconds, minutes
):
    # запись любой длины сохраняется, в том числе 0 с (раньше короче 30 с — 422)
    start(client, user1)
    clock.at = T0 + timedelta(seconds=elapsed)
    stopped = stop(client, user1).json()["stopped"]
    assert (stopped["duration_seconds"], stopped["minutes"]) == (seconds, minutes)


def test_stop_before_start_by_clock_skew_gives_zero(client, user1, clock):
    start(client, user1)
    clock.at = T0 - timedelta(seconds=2)
    stopped = stop(client, user1).json()["stopped"]
    assert stopped["duration_seconds"] == 0
    assert stopped["stopped_at"] == stopped["started_at"]


def test_timer_is_per_user(client, user1, user2):
    entry = start(client, user1).json()["entry"]
    assert current(client, user2)["entry"] is None
    assert stop(client, user2).json()["stopped"] is None
    assert start(client, user2, task_id=1).status_code == 201
    assert current(client, user1)["entry"]["id"] == entry["id"]


def test_admin_has_own_timer(client, user1, admin):
    start(client, user1)
    assert current(client, admin)["entry"] is None
    r = start(client, admin, task_id=7)
    assert r.json()["stopped"] is None
    assert r.json()["entry"]["user_id"] == 99
    assert stop(client, admin).json()["stopped"]["user_id"] == 99
    assert current(client, user1)["entry"] is not None


def test_list_has_old_and_new_fields(client, user1, clock):
    start(client, user1)
    [entry] = client.get("/api/time/time-entries", headers=user1).json()["items"]
    old = {"id", "user_id", "task_id", "minutes", "description", "date", "is_active", "created_at"}
    assert old | {"started_at", "stopped_at", "duration_seconds"} <= entry.keys()
    assert entry["is_active"] is True


def legacy_insert(conn, user_id=1):
    # так пишет старый под в окне выкатки: новых колонок он не знает
    conn.execute(
        text(
            "INSERT INTO time_entries (task_id, user_id, minutes, is_active) "
            "VALUES (1, :u, 5, true)"
        ),
        {"u": user_id},
    )


def test_rows_from_old_pods_are_not_running(client, user1):
    with engine.begin() as conn:
        legacy_insert(conn)
        legacy_insert(conn)
    assert current(client, user1)["entry"] is None
    assert start(client, user1).status_code == 201
    with engine.begin() as conn:
        legacy_insert(conn)
    entries = client.get("/api/time/time-entries", headers=user1).json()["items"]
    assert sorted(e["started_at"] is None for e in entries) == [False, True, True, True]


def assert_one_running_per_user(session_factory):
    with session_factory() as db:
        db.add(TimeEntry(task_id=1, user_id=1, started_at=T0, minutes=1))
        db.add(TimeEntry(task_id=1, user_id=2, started_at=T0, minutes=1))
        db.commit()
        db.add(TimeEntry(task_id=2, user_id=1, started_at=T0, minutes=1))
        with pytest.raises(IntegrityError):
            db.commit()


def test_unique_index_sqlite():
    assert_one_running_per_user(SessionLocal)


def test_unique_index_postgres(pg_app):
    assert_one_running_per_user(sessionmaker(bind=pg_app.engine))


def test_start_retries_once_after_conflict(client, user1, monkeypatch):
    calls = []
    real = crud._start_once

    def flaky(db, user_id, timer_in):
        calls.append(1)
        if len(calls) == 1:
            raise IntegrityError("INSERT", {}, Exception("duplicate key"))
        return real(db, user_id, timer_in)

    monkeypatch.setattr(crud, "_start_once", flaky)
    assert start(client, user1).status_code == 201
    assert len(calls) == 2


def test_start_conflict_twice_is_409(client, user1, monkeypatch):
    calls = []

    def conflict(db, user_id, timer_in):
        calls.append(1)
        raise IntegrityError("INSERT", {}, Exception("duplicate key"))

    monkeypatch.setattr(crud, "_start_once", conflict)
    r = start(client, user1)
    assert r.status_code == 409
    assert r.json() == {"detail": "Timer start conflict, retry"}
    assert len(calls) == 2


def test_parallel_start_on_postgres_keeps_one_running(pg_app):
    Session = sessionmaker(autoflush=False, bind=pg_app.engine)
    # первый старт другой реплики: запись вставлена, транзакция ещё открыта
    first = Session()
    first.add(TimeEntry(task_id=1, user_id=1, started_at=crud.now(), minutes=1))
    first.flush()
    result = {}

    def second():
        with Session() as db:
            entry, stopped, created = crud.start_timer(db, 1, schemas.TimerStart(task_id=2))
            result.update(entry=entry.id, stopped=stopped.id, created=created)

    thread = threading.Thread(target=second)
    thread.start()
    time.sleep(0.5)
    # второй ждёт исхода первой транзакции на уникальном индексе
    assert thread.is_alive()
    first_id = first.scalars(select(TimeEntry.id)).one()
    first.commit()
    first.close()
    thread.join(10)

    # второй получил конфликт, повторил: закрыл запись первого и открыл свою
    assert result == {"entry": result["entry"], "stopped": first_id, "created": True}
    with Session() as db:
        running = db.scalars(select(TimeEntry.id).where(text("stopped_at IS NULL"))).all()
        assert running == [result["entry"]]
        assert db.scalar(select(func.count()).select_from(TimeEntry)) == 2


def test_utc_type_normalizes_read_values():
    utc = UTCDateTime()
    naive = datetime(2026, 10, 22, 23, 59, 50)
    assert utc.process_result_value(naive, None) == naive.replace(tzinfo=UTC)
    moscow = datetime(2026, 10, 23, 2, 59, 50, tzinfo=timezone(timedelta(hours=3)))
    assert utc.process_result_value(moscow, None).tzinfo is UTC
    assert utc.process_bind_param(moscow, None) == naive.replace(tzinfo=UTC)
    assert utc.process_result_value(None, None) is None
    assert utc.process_bind_param(None, None) is None


def test_utc_type_rejects_naive_values():
    with pytest.raises(ValueError, match="naive"):
        UTCDateTime().process_bind_param(datetime(2026, 10, 22), None)


def test_times_read_back_from_sqlite_are_utc(client, user1):
    entry = start(client, user1).json()["entry"]
    again = current(client, user1)["entry"]
    assert again["started_at"] == entry["started_at"]
    assert parse(again["started_at"]).utcoffset() == timedelta(0)
    assert parse(again["created_at"]).utcoffset() == timedelta(0)
