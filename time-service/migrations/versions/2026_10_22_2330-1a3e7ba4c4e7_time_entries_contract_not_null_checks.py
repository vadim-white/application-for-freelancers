"""time_entries contract: started_at NOT NULL, checks, running index

Revision ID: 1a3e7ba4c4e7
Revises: 5ea47ccd8dc7
Create Date: 2026-10-22 23:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1a3e7ba4c4e7"
down_revision: str | Sequence[str] | None = "5ea47ccd8dc7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUNNING = sa.text("stopped_at IS NULL")
RUNNING_EXPAND = sa.text("started_at IS NOT NULL AND stopped_at IS NULL")
CHECKS = {
    "ck_time_entries_stopped_after_started": "stopped_at IS NULL OR stopped_at >= started_at",
    "ck_time_entries_duration_not_negative": "duration_seconds IS NULL OR duration_seconds >= 0",
}

# Записи старых подов из окна expand (только minutes и date) — тем же SQL, что в expand
BACKFILL = {
    "postgresql": """
        UPDATE time_entries SET
            stopped_at = COALESCE(date, created_at, now()),
            started_at = COALESCE(date, created_at, now()) - minutes * interval '1 minute',
            duration_seconds = minutes * 60
        WHERE started_at IS NULL
    """,
    "sqlite": """
        UPDATE time_entries SET
            stopped_at = COALESCE(date, created_at, CURRENT_TIMESTAMP),
            started_at = datetime(COALESCE(date, created_at, CURRENT_TIMESTAMP),
                                  '-' || minutes || ' minutes'),
            duration_seconds = minutes * 60
        WHERE started_at IS NULL
    """,
}


def limit_lock_wait() -> None:
    # ALTER ждёт ACCESS EXCLUSIVE в очереди, и все запросы к таблице встают за ним;
    # запросы приложения короче 5 с, дольше 3 с ждать незачем — Job повторит миграцию
    if op.get_bind().dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")


def upgrade() -> None:
    """Upgrade schema."""
    limit_lock_wait()
    op.execute(BACKFILL[op.get_bind().dialect.name])

    with op.batch_alter_table("time_entries", schema=None) as batch_op:
        batch_op.drop_index("ux_time_entries_running")
        batch_op.alter_column(
            "started_at", existing_type=sa.DateTime(timezone=True), nullable=False
        )
        # новый код is_active не пишет, а старые поды требуют его в ответе
        batch_op.alter_column("is_active", existing_type=sa.Boolean(), server_default=sa.true())
        for name, condition in CHECKS.items():
            batch_op.create_check_constraint(name, condition)
        batch_op.create_index(
            "ux_time_entries_running",
            ["user_id"],
            unique=True,
            sqlite_where=RUNNING,
            postgresql_where=RUNNING,
        )


def downgrade() -> None:
    """Downgrade schema."""
    limit_lock_wait()
    with op.batch_alter_table("time_entries", schema=None) as batch_op:
        batch_op.drop_index("ux_time_entries_running")
        for name in CHECKS:
            batch_op.drop_constraint(name, type_="check")
        batch_op.alter_column("is_active", existing_type=sa.Boolean(), server_default=None)
        batch_op.alter_column("started_at", existing_type=sa.DateTime(timezone=True), nullable=True)
        batch_op.create_index(
            "ux_time_entries_running",
            ["user_id"],
            unique=True,
            sqlite_where=RUNNING_EXPAND,
            postgresql_where=RUNNING_EXPAND,
        )
