"""login_attempts

Revision ID: e8b2cc9410c9
Revises: 6f0e3b36cb48
Create Date: 2026-10-26 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e8b2cc9410c9"
down_revision: str | Sequence[str] | None = "6f0e3b36cb48"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # только новая таблица: старые поды в окне выкатки её не знают и работают как раньше
    op.create_table(
        "login_attempts",
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("email"),
    )
    with op.batch_alter_table("login_attempts", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_login_attempts_window_start"), ["window_start"], unique=False
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("login_attempts", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_login_attempts_window_start"))

    op.drop_table("login_attempts")
