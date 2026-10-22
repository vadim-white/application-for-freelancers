import socket
import threading
import time

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app import ready
from app.db import connect_args

# migrations_db (conftest): пустая база SQLite и, при TEST_POSTGRES_URL, PostgreSQL


@pytest.fixture
def get_ready(client, monkeypatch):
    def _get(engine):
        monkeypatch.setattr(ready, "engine", engine)
        return client.get("/ready")

    return _get


def current_revision(engine):
    with engine.connect() as conn:
        return conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


def test_schema_at_head_is_ready(migrations_db, get_ready):
    migrations_db.run(command.upgrade, "head")
    assert current_revision(migrations_db.engine) == ready.HEAD
    r = get_ready(migrations_db.engine)
    assert r.status_code == 200
    assert r.json() == {"ready": True}


def test_empty_database_is_not_ready(migrations_db, get_ready):
    r = get_ready(migrations_db.engine)
    assert r.status_code == 503
    assert r.json() == {"ready": False, "reason": "schema not migrated"}


def test_downgraded_to_base_is_not_ready(migrations_db, get_ready):
    # таблица alembic_version есть, но пустая
    migrations_db.run(command.upgrade, "head")
    migrations_db.run(command.downgrade, "base")
    r = get_ready(migrations_db.engine)
    assert r.status_code == 503
    assert r.json()["reason"] == "schema not migrated"


# до expand и до contract: новый под не принимает запросы, пока миграция не применена
@pytest.mark.parametrize("revision", ["88fe6764944f", "5ea47ccd8dc7"])
def test_schema_older_than_code_is_not_ready(migrations_db, get_ready, revision):
    migrations_db.run(command.upgrade, revision)
    r = get_ready(migrations_db.engine)
    assert r.status_code == 503
    assert r.json()["reason"] == f"schema revision {revision} is older than code {ready.HEAD}"


def test_unknown_revision_is_ready(migrations_db, get_ready):
    # база новее кода (expand/contract: миграция применена до выката) — под остаётся в балансировке
    migrations_db.run(command.upgrade, "head")
    with migrations_db.engine.begin() as conn:
        conn.execute(text("UPDATE alembic_version SET version_num = 'ffffffffffff'"))
    r = get_ready(migrations_db.engine)
    assert r.status_code == 200


def test_database_unavailable_is_not_ready(migrations_db, get_ready, tmp_path):
    if migrations_db.backend == "sqlite":
        engine = create_engine(f"sqlite:///{tmp_path}/no-such-dir/db.sqlite")
    else:
        # порт, на котором никто не слушает: соединение отклоняется
        url = migrations_db.engine.url.set(port=1)
        engine = create_engine(url, connect_args=connect_args(url.drivername))
    r = get_ready(engine)
    assert r.status_code == 503
    assert r.json() == {"ready": False, "reason": "database unavailable"}


def test_silent_database_fails_within_connect_timeout(get_ready):
    # порт принимает TCP, но молчит — как зависшая база: ответ должен прийти раньше таймаута пробы
    with socket.create_server(("127.0.0.1", 0)) as server:
        # без таймаута соединение ждало бы вечно: закрытие сервера обрывает его, тест падает
        guard = threading.Timer(5, server.close)
        guard.start()
        url = f"postgresql+psycopg://u:p@127.0.0.1:{server.getsockname()[1]}/db"
        engine = create_engine(url, connect_args=connect_args(url))
        started = time.monotonic()
        r = get_ready(engine)
        elapsed = time.monotonic() - started
        guard.cancel()
    assert r.status_code == 503
    assert 1.5 < elapsed < 3


@pytest.mark.parametrize(
    "url, expected",
    [
        ("sqlite:///x.db", {"check_same_thread": False}),
        (
            "postgresql+psycopg://u:p@db/x",
            {
                "connect_timeout": 2,
                "options": "-c statement_timeout=5000",
                "keepalives": 1,
                "keepalives_idle": 5,
                "keepalives_interval": 2,
                "keepalives_count": 3,
                "tcp_user_timeout": 5000,
            },
        ),
        ("mysql://u:p@db/x", {}),
    ],
)
def test_connect_args(url, expected):
    assert connect_args(url) == expected


def test_postgres_connect_args_are_known_to_libpq():
    # опечатка в имени параметра иначе всплыла бы только при соединении с базой
    args = connect_args("postgresql+psycopg://u:p@db/x")
    conninfo = psycopg.conninfo.make_conninfo("", **args)
    assert psycopg.conninfo.conninfo_to_dict(conninfo) == {k: str(v) for k, v in args.items()}


def test_slow_query_is_cancelled_by_statement_timeout(pg_app, client):
    started = time.monotonic()
    with (
        pytest.raises(OperationalError, match="statement timeout"),
        pg_app.engine.connect() as conn,
    ):
        conn.execute(text("SELECT pg_sleep(10)"))
    assert 4.5 < time.monotonic() - started < 7

    # /ready ждёт блокировку alembic_version, как зависший запрос: 503 по statement_timeout
    with pg_app.engine.begin() as locker:
        locker.execute(text("LOCK TABLE alembic_version IN ACCESS EXCLUSIVE MODE"))
        started = time.monotonic()
        r = client.get("/ready")
        elapsed = time.monotonic() - started
    assert r.status_code == 503
    assert r.json()["reason"] == "database unavailable"
    assert 4.5 < elapsed < 7
    assert client.get("/ready").status_code == 200


def test_load_revisions_returns_head_and_its_ancestors(tmp_path):
    # head и предки берутся из цепочки down_revision, а не по имени файла или порядку
    chain = [("a1", None), ("b2", "a1"), ("c3", "b2")]
    (tmp_path / "versions").mkdir()
    for rev, down in chain:
        (tmp_path / "versions" / f"zz_{rev}.py").write_text(
            f"revision = {rev!r}\ndown_revision = {down!r}\n"
        )
    config = Config()
    config.set_main_option("script_location", str(tmp_path))
    assert ready.load_revisions(config) == ("c3", frozenset({"a1", "b2"}))
