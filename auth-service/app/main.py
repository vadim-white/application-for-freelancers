from fastapi import FastAPI

from .api import router as api_router
from .ready import router as ready_router

app = FastAPI(title="Auth Service (auth-service)")

# Таблицы создают миграции (в compose — ser-auth-migrate), тестовых пользователей —
# python -m app.init_users (ser-auth-seed), а не приложение

app.include_router(api_router, prefix="/api/auth")
# /ready вне /api: gateway его не проксирует, проверяют только kubelet и compose
app.include_router(ready_router)


@app.get("/")
async def root():
    return {"service": "auth-service", "status": "ok"}
