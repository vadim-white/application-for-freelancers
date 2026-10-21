import logging
from collections.abc import AsyncIterator, Iterable

import httpx
from fastapi import Request, Response
from fastapi.responses import StreamingResponse

from .core.config import settings

logger = logging.getLogger(__name__)

# Заголовки, которые ставит только gateway; клиентские значения затираются
USER_HEADER_PREFIX = "x-user-"

# RFC 9110, 7.6.1: относятся к одному соединению, прокси их не пересылает
HOP_BY_HOP = frozenset(
    {"connection", "keep-alive", "te", "trailer", "transfer-encoding", "upgrade"}
)

# uvicorn gateway ставит свои; копии от сервиса дали бы по два заголовка
GATEWAY_RESPONSE_HEADERS = frozenset({"date", "server"})

# RFC 9110, 9.2.2: повтор такого запроса не меняет результат
IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE", "PUT", "DELETE"})


def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client


def resolve_upstream(path: str) -> str | None:
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


def drop_hop_by_hop(items: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    """Убирает hop-by-hop заголовки и перечисленные в Connection. Имена — в нижнем регистре."""
    items = list(items)
    listed = {
        token.strip().lower()
        for name, value in items
        if name == "connection"
        for token in value.split(",")
    }
    return [
        (name, value)
        for name, value in items
        if name not in HOP_BY_HOP and name not in listed and not name.startswith("proxy-")
    ]


async def relay_body(r: httpx.Response) -> AsyncIterator[bytes]:
    # закрытие в finally, а не в background: Starlette не вызывает background, если клиент
    # оборвал соединение или upstream упал посреди тела, и соединение не вернулось бы в пул
    try:
        async for chunk in r.aiter_raw():
            yield chunk
    finally:
        await r.aclose()


async def send_upstream(client: httpx.AsyncClient, request: httpx.Request) -> httpx.Response:
    # Соединение из пула может закрыть останавливающийся под сервиса (uvicorn по SIGTERM) в момент
    # отправки. Идемпотентный запрос безопасно повторить, POST — нет: он мог дойти до сервиса.
    try:
        return await client.send(request, stream=True)
    except (httpx.NetworkError, httpx.RemoteProtocolError) as e:
        if request.method not in IDEMPOTENT_METHODS:
            raise
        logger.warning(f"Upstream connection failed, retrying once: {e!r}")
        return await client.send(request, stream=True)


async def stream_proxy(
    request: Request, base_url: str, user: dict | None, client: httpx.AsyncClient
) -> Response:
    target_url = base_url + request.url.path
    if request.url.query:
        target_url = target_url + "?" + request.url.query

    logger.info(f"Proxying {request.method} {request.url.path} -> {target_url}")

    # build headers to forward (exclude host and client-supplied X-User-*)
    headers = [
        (k, v)
        for k, v in drop_hop_by_hop(request.headers.items())
        if k != "host" and not k.startswith(USER_HEADER_PREFIX)
    ]

    if user is not None:
        headers.append(("X-User-Id", user["id"]))
        headers.append(("X-User-Role", user["role"]))

    body = await request.body()

    # Если есть body, убедимся что Content-Type установлен правильно
    if body and all(k != "content-type" for k, _ in headers):
        headers.append(("Content-Type", "application/json"))
        logger.debug("Added Content-Type: application/json")

    upstream_request = client.build_request(
        method=request.method, url=target_url, headers=headers, content=body
    )
    try:
        r = await send_upstream(client, upstream_request)
        logger.info(f"Upstream response: {r.status_code}")
    except httpx.TimeoutException as e:
        logger.error(f"Upstream request timed out: {e!r}")
        return Response(content="Upstream service timeout", status_code=504)
    except httpx.RequestError as e:
        logger.error(f"Upstream request failed: {e!r}")
        return Response(content="Upstream service unavailable", status_code=502)

    response = StreamingResponse(relay_body(r), status_code=r.status_code)
    # тело идёт сырым (aiter_raw), поэтому content-encoding и content-length сервиса верны как есть;
    # raw_headers вместо dict: повторяющиеся заголовки (set-cookie) не склеиваются
    response.raw_headers = [
        (k.encode("latin-1"), v.encode("latin-1"))
        for k, v in drop_hop_by_hop(r.headers.multi_items())
        if k not in GATEWAY_RESPONSE_HEADERS
    ]
    return response
