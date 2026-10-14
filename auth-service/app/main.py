from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api import router as api_router
from .db import Base, engine, SessionLocal
from .init_users import init_test_users
from .core.config import settings

app = FastAPI(title="Auth Service (auth-service)")

# CORS - подберите origin в production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Инициализация БД при старте
@app.on_event("startup")
async def startup_event():
    Base.metadata.create_all(bind=engine)

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
