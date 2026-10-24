"""user_audit

Revision ID: 6f0e3b36cb48
Revises: 37998bcc3290
Create Date: 2026-10-24 21:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6f0e3b36cb48"
down_revision: str | Sequence[str] | None = "37998bcc3290"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # только новая таблица: старые поды в окне выкатки её не знают и работают как раньше
    op.create_table(
        "user_audit",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("field", sa.String(), nullable=False),
        sa.Column("old_value", sa.String(), nullable=False),
        sa.Column("new_value", sa.String(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["target_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("user_audit", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_user_audit_target_id"), ["target_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("user_audit", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_user_audit_target_id"))

    op.drop_table("user_audit")
