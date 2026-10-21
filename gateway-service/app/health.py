import asyncio

import httpx
from fastapi import APIRouter, Depends

from .core.config import settings
from .proxy import get_http_client

router = APIRouter()

HEALTH_TIMEOUT = 2.0


async def _is_up(client: httpx.AsyncClient, url: str) -> bool:
    try:
        r = await client.get(url + "/", timeout=HEALTH_TIMEOUT)
        return r.status_code == 200
    except Exception:
        return False


@router.get("/health")
async def health(client: httpx.AsyncClient = Depends(get_http_client)):
    names = ("auth", "task", "time")
    urls = (settings.AUTH_URL, settings.TASK_URL, settings.TIME_URL)
    results = await asyncio.gather(*(_is_up(client, url) for url in urls))
    return {"gateway": "ok", "upstreams": dict(zip(names, results, strict=True))}
