from fastapi import FastAPI
from .api import router as api_router
from .db import SessionLocal
from .init_users import init_test_users
from .core.config import settings

app = FastAPI(title="Auth Service (auth-service)")

# Таблицы создаёт не приложение, а миграции: alembic upgrade head (в compose — сервис ser-auth-migrate)
@app.on_event("startup")
async def startup_event():
    # Тестовые пользователи с известными паролями — только для разработки
    if not settings.SEED_TEST_USERS:
        return
    db = SessionLocal()
    try:
        init_test_users(db)
    except Exception as e:
        print(f"Error initializing test users: {e}")
    finally:
        db.close()

app.include_router(api_router, prefix="/api/auth")

@app.get("/")
async def root():
    return {"service": "auth-service", "status": "ok"}
