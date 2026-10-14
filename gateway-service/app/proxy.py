import httpx
from fastapi import Request, Response
from typing import Dict, Optional
from .core.config import settings
import logging

logger = logging.getLogger(__name__)

# Заголовки, которые ставит только gateway; клиентские значения затираются
USER_HEADER_PREFIX = "x-user-"


def resolve_upstream(path: str) -> Optional[str]:
    """Базовый адрес сервиса для пути /api/{auth,tasks,time}/... или None для неизвестного пути."""
    # точечные сегменты не пропускаем: httpx нормализует их и запрос уйдёт не туда, где проверялся
    if any(segment in (".", "..") for segment in path.split("/")):
        return None
    routes = {
        "/api/auth": settings.AUTH_URL,
        "/api/tasks": settings.TASK_URL,
        "/api/time": settings.TIME_URL,
    }
    for prefix, base in routes.items():
        if path == prefix or path.startswith(prefix + "/"):
            return base
    return None


async def stream_proxy(request: Request, base_url: str, user: Optional[dict]) -> Response:
    target_url = base_url + request.url.path
    if request.url.query:
        target_url = target_url + "?" + request.url.query

    logger.info(f"Proxying {request.method} {request.url.path} -> {target_url}")

    # build headers to forward (exclude host and client-supplied X-User-*)
    headers: Dict[str, str] = {}
    for k, v in request.headers.items():
        lower = k.lower()
        if lower == "host" or lower.startswith(USER_HEADER_PREFIX):
            continue
        headers[k] = v

    if user is not None:
        headers["X-User-Id"] = user["id"]
        headers["X-User-Role"] = user["role"]

    async with httpx.AsyncClient(timeout=30.0) as client:
        # read body (async)
        body = await request.body()

        # Если есть body, убедимся что Content-Type установлен правильно
        if body and "content-type" not in {k.lower() for k in headers.keys()}:
            headers["Content-Type"] = "application/json"
            logger.debug("Added Content-Type: application/json")

        try:
            r = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
            )
            logger.info(f"Upstream response: {r.status_code}")
        except httpx.RequestError as e:
            logger.error(f"Upstream request failed: {e}")
            return Response(content="Upstream service unavailable", status_code=502)

    # build FastAPI response with upstream status and headers
    response_headers = dict(r.headers)

    # remove hop-by-hop headers if needed
    for h in ["transfer-encoding", "content-encoding", "connection", "keep-alive"]:
        response_headers.pop(h, None)

    return Response(content=r.content, status_code=r.status_code, headers=response_headers)
