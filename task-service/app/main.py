from fastapi import FastAPI
from .api import router as api_router

app = FastAPI(title="Task Service (task-service)")

# Таблицы создаёт не приложение, а миграции: alembic upgrade head (в compose — сервис ser-task-migrate)
app.include_router(api_router, prefix="/api/tasks")

@app.get("/")
async def root():
    return {"service": "task-service", "status": "ok"}
