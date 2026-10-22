from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from .api import router as api_router
from .core.config import settings
from .ready import router as ready_router
from .time_client import TIME_TIMEOUT


@asynccontextmanager
async def lifespan(app: FastAPI):
    # один клиент на процесс: пул keep-alive соединений к time вместо нового TCP на запрос
    async with httpx.AsyncClient(
        base_url=settings.TIME_SERVICE_URL, timeout=TIME_TIMEOUT
    ) as client:
        app.state.time_client = client
        yield


app = FastAPI(title="Task Service (task-service)", lifespan=lifespan)

# Таблицы создаёт не приложение, а миграции: alembic upgrade head
# (в compose — сервис ser-task-migrate)
app.include_router(api_router, prefix="/api/tasks")
# /ready вне /api: gateway его не проксирует, проверяют только kubelet и compose
app.include_router(ready_router)


@app.get("/")
async def root():
    return {"service": "task-service", "status": "ok"}
