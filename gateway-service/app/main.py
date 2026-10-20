from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from .core.config import settings
from .health import router as health_router
from .middleware import authenticate
from .proxy import get_http_client, resolve_upstream, stream_proxy

# connect короче общего: недоступный сервис виден за 5 с, а не за 30
UPSTREAM_TIMEOUT = httpx.Timeout(30.0, connect=5.0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # один клиент на процесс: пул keep-alive соединений к сервисам вместо нового TCP на запрос
    async with httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT) as client:
        app.state.http_client = client
        yield


app = FastAPI(title="API Gateway", lifespan=lifespan)

# CORS нужен только здесь: браузер ходит в gateway, внутренние сервисы ему недоступны.
# Токен передаётся в заголовке Authorization, cookies не используются.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# health check
app.include_router(health_router)


# catch-all proxy route: all paths under /api/*
# Неизвестные пути -> 404, всё кроме публичных эндпоинтов auth требует Bearer access-токен.
@app.api_route(
    "/api/{full_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
)
async def proxy(
    full_path: str, request: Request, client: httpx.AsyncClient = Depends(get_http_client)
):
    base_url = resolve_upstream(request.url.path)
    if base_url is None:
        raise HTTPException(status_code=404, detail="Not found")
    user = authenticate(request)
    return await stream_proxy(request, base_url, user, client)


@app.get("/")
async def root():
    return {"service": "gateway", "status": "ok"}
