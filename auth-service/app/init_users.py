"""
Тестовые пользователи для разработки: python -m app.init_users

Создаёт пользователей только при SEED_TEST_USERS=true, иначе пишет «пропущено» и выходит с кодом 0.
Таблицы должны уже существовать (alembic upgrade head). Повторный запуск не создаёт дублей.
"""

import logging

from sqlalchemy.orm import Session

from . import models
from .core.config import settings
from .core.security import get_password_hash
from .db import SessionLocal
from .models import UserRole

logger = logging.getLogger("app.init_users")

# Тестовые пользователи
TEST_USERS = [
    {
        "email": "admin@example.com",
        "full_name": "Admin User",
        "password": "password123",
        "role": UserRole.admin,
    },
    {
        "email": "user1@example.com",
        "full_name": "User One",
        "password": "password123",
        "role": UserRole.user,
    },
    {
        "email": "user2@example.com",
        "full_name": "User Two",
        "password": "password123",
        "role": UserRole.user,
    },
]


def init_test_users(db: Session):
    """Создать тестовых пользователей, которых ещё нет"""
    for user_data in TEST_USERS:
        existing_user = (
            db.query(models.User).filter(models.User.email == user_data["email"]).first()
        )

        if not existing_user:
            db.add(
                models.User(
                    email=user_data["email"],
                    full_name=user_data["full_name"],
                    hashed_password=get_password_hash(user_data["password"]),
                    role=user_data["role"],
                )
            )
            logger.info("Создан пользователь %s (%s)", user_data["email"], user_data["role"].value)
        else:
            logger.info("Пользователь уже есть: %s", user_data["email"])

    db.commit()


def main():
    if not settings.SEED_TEST_USERS:
        logger.info("SEED_TEST_USERS не включён, создание тестовых пользователей пропущено")
        return
    db = SessionLocal()
    try:
        init_test_users(db)
    except Exception:
        db.rollback()
        logger.exception("Не удалось создать тестовых пользователей")
        raise
    finally:
        db.close()
    logger.info("Тестовые пользователи готовы")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    main()
