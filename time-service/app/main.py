from fastapi import FastAPI
from .db import Base, engine
from .api import router as time_router
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Time Service")

# Инициализация БД при старте
@app.on_event("startup")
async def startup_event():
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created or already exist")

app.include_router(time_router, prefix="/api/time")

@app.get("/")
async def root():
    return {"service": "time-service", "status": "ok"}