"""time_entries: drop minutes, date, is_active

Revision ID: 30ac5e04a1c1
Revises: 1a3e7ba4c4e7
Create Date: 2026-10-23 08:19:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "30ac5e04a1c1"
down_revision: str | Sequence[str] | None = "1a3e7ba4c4e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def limit_lock_wait() -> None:
    # DROP COLUMN ждёт ACCESS EXCLUSIVE в очереди, и все запросы к таблице встают за ним;
    # запросы приложения короче 5 с, дольше 3 с ждать незачем — Job повторит миграцию
    if op.get_bind().dialect.name == "postgresql":
        op.execute("SET LOCAL lock_timeout = '3s'")


def upgrade() -> None:
    """Upgrade schema."""
    limit_lock_wait()
    with op.batch_alter_table("time_entries", schema=None) as batch_op:
        batch_op.drop_column("is_active")
        batch_op.drop_column("date")
        batch_op.drop_column("minutes")


def downgrade() -> None:
    """Downgrade schema."""
    # nullable: у записей после contract minutes и date нет, код contract их не читает;
    # is_active заполняется true — код до contract требует его в ответе
    limit_lock_wait()
    with op.batch_alter_table("time_entries", schema=None) as batch_op:
        batch_op.add_column(sa.Column("minutes", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("date", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(
            sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=True)
        )
    # default отдельно: иначе старые строки получили бы date = время отката
    with op.batch_alter_table("time_entries", schema=None) as batch_op:
        batch_op.alter_column(
            "date", existing_type=sa.DateTime(timezone=True), server_default=sa.func.now()
        )
