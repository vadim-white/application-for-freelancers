import httpx
from fastapi import APIRouter

from .core.config import settings

router = APIRouter()

@router.get("/health")
async def health():
    # check upstream services quickly
    ok = {}
    async with httpx.AsyncClient(timeout=2.0) as client:
        try:
            r = await client.get(settings.AUTH_URL + "/")
            ok["auth"] = r.status_code == 200
        except Exception:
            ok["auth"] = False
        try:
            r = await client.get(settings.TASK_URL + "/")
            ok["task"] = r.status_code == 200
        except Exception:
            ok["task"] = False
        try:
            r = await client.get(settings.TIME_URL + "/")
            ok["time"] = r.status_code == 200
        except Exception:
            ok["time"] = False
    return {"gateway": "ok", "upstreams": ok}
