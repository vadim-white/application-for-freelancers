"""
Инициализация тестовых пользователей в БД
"""
from sqlalchemy.orm import Session
from . import models
from .models import UserRole
from .core.security import get_password_hash
from .db import SessionLocal

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
    """Создать тестовых пользователей если их еще нет"""
    for user_data in TEST_USERS:
        # Проверить есть ли уже такой пользователь
        existing_user = db.query(models.User).filter(
            models.User.email == user_data["email"]
        ).first()
        
        if not existing_user:
            new_user = models.User(
                email=user_data["email"],
                full_name=user_data["full_name"],
                hashed_password=get_password_hash(user_data["password"]),
                role=user_data["role"],
            )
            db.add(new_user)
            role_name = "Admin" if user_data["role"] == UserRole.admin else "User"
            print(f"✅ Created user: {user_data['email']} ({role_name})")
        else:
            role_name = "Admin" if user_data["role"] == UserRole.admin else "User"
            print(f"⏭️  User already exists: {user_data['email']} ({role_name})")
    
    db.commit()

def initialize_database():
    """Инициализация БД с тестовыми пользователями"""
    db = SessionLocal()
    try:
        print("🚀 Initializing test users...")
        init_test_users(db)
        print("✨ Database initialization complete!")
    except Exception as e:
        print(f"❌ Error initializing database: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    initialize_database()
