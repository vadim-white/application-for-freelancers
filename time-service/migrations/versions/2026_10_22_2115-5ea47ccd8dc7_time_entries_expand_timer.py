"""time_entries expand: started_at, stopped_at, duration_seconds

Revision ID: 5ea47ccd8dc7
Revises: 88fe6764944f
Create Date: 2026-10-22 21:15:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5ea47ccd8dc7"
down_revision: str | Sequence[str] | None = "88fe6764944f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUNNING = sa.text("started_at IS NOT NULL AND stopped_at IS NULL")

# Старая запись сохранялась при остановке: date — её конец, minutes — длительность.
# Заполняем здесь, а не в коде сервиса: у запросов приложения лимит 5 с, у миграции его нет
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


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("time_entries", schema=None) as batch_op:
        batch_op.add_column(sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("duration_seconds", sa.Integer(), nullable=True))
        batch_op.alter_column("minutes", existing_type=sa.Integer(), nullable=True)

    op.execute(BACKFILL[op.get_bind().dialect.name])

    with op.batch_alter_table("time_entries", schema=None) as batch_op:
        batch_op.create_index(
            "ux_time_entries_running",
            ["user_id"],
            unique=True,
            sqlite_where=RUNNING,
            postgresql_where=RUNNING,
        )
        batch_op.create_index(
            "ix_time_entries_user_id_started_at", ["user_id", "started_at"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_time_entries_task_id"), ["task_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("time_entries", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_time_entries_task_id"))
        batch_op.drop_index("ix_time_entries_user_id_started_at")
        batch_op.drop_index("ux_time_entries_running")

    # minutes новый код пишет всегда (dual write), NOT NULL возвращается без заполнения
    with op.batch_alter_table("time_entries", schema=None) as batch_op:
        batch_op.alter_column("minutes", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_column("duration_seconds")
        batch_op.drop_column("stopped_at")
        batch_op.drop_column("started_at")
