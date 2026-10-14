from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app import models  # noqa: F401  регистрирует таблицы в Base.metadata
from app.core.config import settings
from app.db import Base

config = context.config

if config.config_file_name is not None:
    # disable_existing_loggers=False: не глушить логгеры приложения, если миграции запущены из кода
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata

# render_as_batch: в SQLite ALTER TABLE ограничен, Alembic пересоздаёт таблицу
# compare_type: autogenerate и alembic check замечают смену типа колонки
CONFIGURE_OPTS = {"target_metadata": target_metadata, "render_as_batch": True, "compare_type": True}


def run_migrations_offline() -> None:
    """SQL в stdout без подключения к базе (alembic upgrade head --sql)."""
    context.configure(
        url=settings.DATABASE_URL,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **CONFIGURE_OPTS,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, **CONFIGURE_OPTS)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Готовое соединение передают через config.attributes (тесты), иначе подключаемся по DATABASE_URL
    connection = config.attributes.get("connection")
    if connection is not None:
        do_run_migrations(connection)
        return

    engine = create_engine(settings.DATABASE_URL, poolclass=pool.NullPool)
    with engine.connect() as connection:
        do_run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
