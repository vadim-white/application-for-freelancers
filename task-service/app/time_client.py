import httpx
from fastapi import Request

# ответ time ограничен statement_timeout базы (5 с): запас сверху, но меньше таймаута gateway (30 с)
TIME_TIMEOUT = httpx.Timeout(7.0, connect=2.0)


def get_time_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.time_client
