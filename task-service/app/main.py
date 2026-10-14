from fastapi import FastAPI
from .api import router as api_router
from .db import Base, engine

app = FastAPI(title="Task Service (task-service)")

# Инициализация БД при старте
@app.on_event("startup")
async def startup_event():
    Base.metadata.create_all(bind=engine)

app.include_router(api_router, prefix="/api/tasks")

@app.get("/")
async def root():
    return {"service": "task-service", "status": "ok"}
