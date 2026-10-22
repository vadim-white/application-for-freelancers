import logging

import httpx
from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

# старт таймера ждёт task: недоступный task — 503 за секунды, а не висящий запрос
TASK_TIMEOUT = httpx.Timeout(3.0, connect=2.0)


def get_task_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.task_client


async def fetch_usable_task(client: httpx.AsyncClient, task_id: int, authorization: str) -> dict:
    """Задача из task-service, если на неё можно писать время; иначе HTTPException.

    Токен пользователя: task сам решает, чья задача (чужая — 404, admin видит все).
    """
    try:
        r = await client.get(
            f"/api/tasks/tasks/{task_id}", headers={"Authorization": authorization}
        )
    except httpx.HTTPError as e:
        logger.warning(f"Task service request failed: {e!r}")
        raise HTTPException(status_code=503, detail="Task service unavailable") from e
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="Task not found")
    if r.status_code >= 500:
        logger.warning(f"Task service answered {r.status_code}")
        raise HTTPException(status_code=503, detail="Task service unavailable")
    if r.status_code != 200:
        # тот же токен уже принят здесь: 401/403 от task — рассинхрон настроек, а не ошибка клиента
        logger.error(f"Task service rejected request: {r.status_code}")
        raise HTTPException(status_code=502, detail="Task service rejected request")
    task = r.json()
    project = task.get("project")
    if task.get("is_active") is False or (project and project.get("is_active") is False):
        raise HTTPException(status_code=409, detail="Task is archived")
    return task
