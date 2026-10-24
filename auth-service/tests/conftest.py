import os
import pathlib
import tempfile
import uuid
from types import SimpleNamespace

# Окружение задаётся до импорта приложения: config и engine создаются при импорте
os.environ["SECRET_KEY"] = "test-secret-key-at-least-32-bytes-long"
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/auth_test.db"
os.environ["SEED_TEST_USERS"] = "false"

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker

from app import deps, models, ready
from app.core.security import get_password_hash
from app.db import Base, SessionLocal, engine, make_engine
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
    def _make(
        email="user@example.com",
        role=models.UserRole.user,
        is_active=True,
        full_name=None,
        created_at=None,
    ):
        user = models.User(
            email=email,
            hashed_password=get_password_hash(PASSWORD),
            role=role,
            is_active=is_active,
            full_name=full_name,
            created_at=created_at,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    return _make


def login(client, email="user@example.com", password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


SERVICE_ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(params=["sqlite", "postgres"])
def migrations_db(request, tmp_path):
    """Пустая база для миграций: DATABASE_URL из conftest занят базой остальных тестов.

    sqlite — отдельный файл. postgres — своя схема (search_path) в базе из TEST_POSTGRES_URL
    (postgresql+psycopg://…), она создаётся перед тестом и удаляется после;
    без переменной тест пропускается.
    Соединение передаётся в migrations/env.py через cfg.attributes["connection"].
    """
    schema = None
    if request.param == "sqlite":
        engine = create_engine(f"sqlite:///{tmp_path}/migrations.db")
    else:
        url = os.environ.get("TEST_POSTGRES_URL")
        if not url:
            pytest.skip("TEST_POSTGRES_URL не задана: тест на PostgreSQL пропущен")
        schema = f"mig_{uuid.uuid4().hex[:12]}"
        admin = create_engine(url, isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            conn.execute(text(f"CREATE SCHEMA {schema}"))
        # таблицы и типы enum создаются в этой схеме и не мешают остальным базам и тестам
        engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    cfg = Config(str(SERVICE_ROOT / "alembic.ini"))

    def run(cmd, *args):
        with engine.begin() as connection:
            cfg.attributes["connection"] = connection
            cmd(cfg, *args)

    def tables():
        return set(inspect(engine).get_table_names())

    def enums():
        """Имена типов enum в схеме теста (в SQLite типов нет)."""
        if schema is None:
            return set()
        query = text(
            "SELECT t.typname FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace "
            "WHERE n.nspname = :schema AND t.typtype = 'e'"
        )
        with engine.connect() as conn:
            return set(conn.execute(query, {"schema": schema}).scalars())

    # база чистая до теста
    assert tables() == set()
    assert enums() == set()

    yield SimpleNamespace(backend=request.param, engine=engine, run=run, tables=tables, enums=enums)

    engine.dispose()
    if schema is not None:
        with admin.connect() as conn:
            conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()


@pytest.fixture
def pg_app(monkeypatch):
    """Приложение на PostgreSQL из TEST_POSTGRES_URL: движок из make_engine, своя схема на head.

    Сессии API и /ready идут через этот движок; без переменной тест пропускается.
    terminate() обрывает его соединения со стороны сервера — как перезапуск базы.
    """
    url = os.environ.get("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("TEST_POSTGRES_URL не задана: тест на PostgreSQL пропущен")
    schema = f"app_{uuid.uuid4().hex[:12]}"
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"CREATE SCHEMA {schema}"))
    engine = make_engine(url)
    pids = []

    # options занят statement_timeout, поэтому схема задаётся командой после соединения
    @event.listens_for(engine, "connect")
    def on_connect(dbapi_conn, _record):
        dbapi_conn.execute(f"SET search_path TO {schema}")
        dbapi_conn.commit()
        pids.append(dbapi_conn.info.backend_pid)

    cfg = Config(str(SERVICE_ROOT / "alembic.ini"))
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")

    def terminate():
        with admin.connect() as conn:
            query = text(
                "SELECT count(*) FILTER (WHERE pg_terminate_backend(pid)) FROM unnest(:pids) AS pid"
            )
            return conn.execute(query, {"pids": pids}).scalar_one()

    monkeypatch.setattr(deps, "SessionLocal", sessionmaker(autoflush=False, bind=engine))
    monkeypatch.setattr(ready, "engine", engine)
    yield SimpleNamespace(engine=engine, terminate=terminate)

    engine.dispose()
    with admin.connect() as conn:
        conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
    admin.dispose()
