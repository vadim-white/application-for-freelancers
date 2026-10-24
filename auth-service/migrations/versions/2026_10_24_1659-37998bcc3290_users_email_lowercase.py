"""users: email to lowercase

Revision ID: 37998bcc3290
Revises: d68b21b4476c
Create Date: 2026-10-24 16:59:22.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "37998bcc3290"
down_revision: str | Sequence[str] | None = "d68b21b4476c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    query = sa.text(
        "SELECT lower(email) FROM users GROUP BY lower(email) HAVING count(*) > 1 ORDER BY 1"
    )
    duplicates = op.get_bind().execute(query).scalars().all()
    # какой из аккаунтов оставить, решает человек: миграция ничего не сливает и не удаляет
    if duplicates:
        raise RuntimeError(
            "Адреса, совпадающие без учёта регистра, — объедините или переименуйте аккаунты "
            f"вручную и повторите миграцию: {', '.join(duplicates)}"
        )
    op.execute("UPDATE users SET email = lower(email) WHERE email <> lower(email)")


def downgrade() -> None:
    """Downgrade schema."""
    # Исходный регистр не сохранён, вернуть его нельзя; схема в upgrade не менялась
