"""create time_entries

Revision ID: 88fe6764944f
Revises:
Create Date: 2026-10-14 15:23:14.150753

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "88fe6764944f"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "time_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        # func.now(), а не text('now()'): в SQLite нет now(), диалект подставит CURRENT_TIMESTAMP
        sa.Column("date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("time_entries", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_time_entries_id"), ["id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("time_entries", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_time_entries_id"))

    op.drop_table("time_entries")
