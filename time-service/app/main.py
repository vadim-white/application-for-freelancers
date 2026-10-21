import logging

from fastapi import FastAPI

from .api import router as time_router
from .ready import router as ready_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Time Service")

# Таблицы создаёт не приложение, а миграции: alembic upgrade head
# (в compose — сервис ser-time-migrate)
app.include_router(time_router, prefix="/api/time")
# /ready вне /api: gateway его не проксирует, проверяют только kubelet и compose
app.include_router(ready_router)


@app.get("/")
async def root():
    return {"service": "time-service", "status": "ok"}
