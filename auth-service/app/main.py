from fastapi import FastAPI

from .api import router as api_router
from .ready import router as ready_router

app = FastAPI(title="Auth Service (auth-service)")

# Таблицы создаёт не приложение, а миграции: alembic upgrade head
# (в compose — сервис ser-auth-migrate).
# Тестовых пользователей создаёт отдельная команда python -m app.init_users
# (в compose — ser-auth-seed)

app.include_router(api_router, prefix="/api/auth")
# /ready вне /api: gateway его не проксирует, проверяют только kubelet и compose
app.include_router(ready_router)


@app.get("/")
async def root():
    return {"service": "auth-service", "status": "ok"}
