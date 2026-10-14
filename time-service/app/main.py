from fastapi import FastAPI
from .api import router as time_router
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Time Service")

# Таблицы создаёт не приложение, а миграции: alembic upgrade head (в compose — сервис ser-time-migrate)
app.include_router(time_router, prefix="/api/time")

@app.get("/")
async def root():
    return {"service": "time-service", "status": "ok"}