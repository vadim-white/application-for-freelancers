"""create projects and tasks

Revision ID: 9c3410dbc910
Revises:
Create Date: 2026-10-14 16:10:40.770212

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9c3410dbc910"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        # func.now(), а не text('now()'): в SQLite нет now(), диалект подставит CURRENT_TIMESTAMP
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_projects_id"), ["id"], unique=False)
        batch_op.create_index(batch_op.f("ix_projects_owner_id"), ["owner_id"], unique=False)

    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        # В PostgreSQL create_table создаёт тип taskstatus
        sa.Column(
            "status",
            sa.Enum("todo", "in_progress", "done", "blocked", name="taskstatus"),
            nullable=False,
        ),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        # tasks ссылается на projects: создаётся после неё, удаляется раньше
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_tasks_id"), ["id"], unique=False)
        batch_op.create_index(batch_op.f("ix_tasks_owner_id"), ["owner_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_tasks_owner_id"))
        batch_op.drop_index(batch_op.f("ix_tasks_id"))

    op.drop_table("tasks")
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_projects_owner_id"))
        batch_op.drop_index(batch_op.f("ix_projects_id"))

    op.drop_table("projects")
    # drop_table не удаляет тип enum в PostgreSQL. В SQLite типа нет, вызов ничего не делает
    sa.Enum(name="taskstatus").drop(op.get_bind(), checkfirst=True)
