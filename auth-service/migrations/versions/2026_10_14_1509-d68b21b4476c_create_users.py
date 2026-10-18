"""create users

Revision ID: d68b21b4476c
Revises:
Create Date: 2026-10-14 15:09:11.259291

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d68b21b4476c"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("hashed_password", sa.String(), nullable=False),
        # func.now(), а не text('now()'): в SQLite нет now(), диалект подставит CURRENT_TIMESTAMP
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True
        ),
        sa.Column("full_name", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        # В PostgreSQL create_table создаёт тип userrole
        sa.Column("role", sa.Enum("user", "admin", name="userrole"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_users_email"), ["email"], unique=True)
        batch_op.create_index(batch_op.f("ix_users_id"), ["id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_users_id"))
        batch_op.drop_index(batch_op.f("ix_users_email"))

    op.drop_table("users")
    # drop_table не удаляет тип enum в PostgreSQL. В SQLite типа нет, вызов ничего не делает
    sa.Enum(name="userrole").drop(op.get_bind(), checkfirst=True)
