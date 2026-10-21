from fastapi import FastAPI

from .api import router as api_router
from .ready import router as ready_router

app = FastAPI(title="Task Service (task-service)")

# Таблицы создаёт не приложение, а миграции: alembic upgrade head
# (в compose — сервис ser-task-migrate)
app.include_router(api_router, prefix="/api/tasks")
# /ready вне /api: gateway его не проксирует, проверяют только kubelet и compose
app.include_router(ready_router)


@app.get("/")
async def root():
    return {"service": "task-service", "status": "ok"}
