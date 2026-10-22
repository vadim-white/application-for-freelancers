import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from .api import router as time_router
from .core.config import settings
from .ready import router as ready_router
from .task_client import TASK_TIMEOUT

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # один клиент на процесс: пул keep-alive соединений к task вместо нового TCP на запрос
    async with httpx.AsyncClient(
        base_url=settings.TASK_SERVICE_URL, timeout=TASK_TIMEOUT
    ) as client:
        app.state.task_client = client
        yield


app = FastAPI(title="Time Service", lifespan=lifespan)

# Таблицы создаёт не приложение, а миграции: alembic upgrade head
# (в compose — сервис ser-time-migrate)
app.include_router(time_router, prefix="/api/time")
# /ready вне /api: gateway его не проксирует, проверяют только kubelet и compose
app.include_router(ready_router)


@app.get("/")
async def root():
    return {"service": "time-service", "status": "ok"}
