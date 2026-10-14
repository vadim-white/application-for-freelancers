import httpx
from fastapi import Request, Response
from fastapi.responses import StreamingResponse
from typing import Dict
from .core.config import settings
import logging

logger = logging.getLogger(__name__)

# helper to build target URL based on incoming path
def _route_to_target(path: str) -> str:
    # incoming paths: /api/auth/..., /api/tasks/..., /api/time/...
    if path.startswith("/api/auth"):
        base = settings.AUTH_URL
    elif path.startswith("/api/tasks"):
        base = settings.TASK_URL
    elif path.startswith("/api/time"):
        base = settings.TIME_URL
    else:
        # default: health or unknown
        base = settings.AUTH_URL
    # forward same path and query
    return base + path

async def stream_proxy(request: Request) -> Response:
    target_url = _route_to_target(str(request.url.path))
    if request.url.query:
        target_url = target_url + "?" + request.url.query

    logger.info(f"Proxying {request.method} {request.url.path} -> {target_url}")

    # build headers to forward (exclude host)
    headers: Dict[str, str] = {}
    for k, v in request.headers.items():
        if k.lower() == "host":
            continue
        headers[k] = v
    
    logger.debug(f"Forwarding headers: {dict(list(headers.items())[:5])}")  # log first 5 headers

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
            return Response(content=f"Upstream request failed: {e}", status_code=502)

    # build FastAPI response with upstream status and headers
    response_headers = dict(r.headers)

    # remove hop-by-hop headers if needed
    for h in ["transfer-encoding", "content-encoding", "connection", "keep-alive"]:
        response_headers.pop(h, None)

    return Response(content=r.content, status_code=r.status_code, headers=response_headers)
