import asyncio
import gc
import gzip

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.requests import ClientDisconnect

from app import main
from app.main import app
from tests.conftest import as_network_stream, bearer, make_token

# --- общий клиент ---


def test_one_client_per_app(monkeypatch):
    created = []
    real_client = httpx.AsyncClient

    def counting_client(*args, **kwargs):
        handler = as_network_stream(lambda request: httpx.Response(200))
        kwargs["transport"] = httpx.MockTransport(handler)
        created.append(real_client(*args, **kwargs))
        return created[-1]

    monkeypatch.setattr(main.httpx, "AsyncClient", counting_client)
    with TestClient(app) as c:
        for _ in range(3):
            assert c.get("/api/tasks/projects", headers=bearer(make_token())).status_code == 200
        assert c.get("/health").json()["upstreams"] == {"auth": True, "task": True, "time": True}
        assert len(created) == 1
        assert created[0].timeout == httpx.Timeout(30.0, connect=5.0)
    assert created[0].is_closed


def test_health_checks_run_in_parallel(client, mock_upstream):
    barrier = asyncio.Barrier(3)
    timeouts = []

    async def handler(request: httpx.Request) -> httpx.Response:
        timeouts.append(request.extensions["timeout"])
        # при последовательных проверках барьер не дождётся остальных
        await asyncio.wait_for(barrier.wait(), timeout=1)
        return httpx.Response(200)

    mock_upstream(handler)
    r = client.get("/health")
    assert r.json()["upstreams"] == {"auth": True, "task": True, "time": True}
    assert timeouts == [dict.fromkeys(("connect", "read", "write", "pool"), 2.0)] * 3


# --- заголовки ---


def test_response_drops_hop_by_hop_and_gateway_headers(client, mock_upstream):
    upstream_headers = [
        ("date", "Sun, 18 Oct 2026 17:23:20 GMT"),
        ("server", "uvicorn"),
        ("connection", "keep-alive, x-hop"),
        ("keep-alive", "timeout=5"),
        ("x-hop", "1"),
        ("upgrade", "h2c"),
        ("trailer", "x-checksum"),
        ("proxy-authenticate", "Basic"),
        ("x-request-id", "abc"),
        ("set-cookie", "a=1"),
        ("set-cookie", "b=2"),
    ]
    mock_upstream(lambda request: httpx.Response(200, headers=upstream_headers, json={}))
    r = client.get("/api/tasks/projects", headers=bearer(make_token()))
    assert r.status_code == 200
    # date и server ставит uvicorn gateway (в TestClient его нет)
    for name in ("date", "server", "connection", "keep-alive", "x-hop", "upgrade", "trailer"):
        assert name not in r.headers, name
    assert "proxy-authenticate" not in r.headers
    assert r.headers["x-request-id"] == "abc"
    assert r.headers.get_list("set-cookie") == ["a=1", "b=2"]
    assert r.headers["content-type"] == "application/json"


def test_request_drops_hop_by_hop(client, upstream):
    token = make_token()
    client.get(
        "/api/tasks/projects",
        headers={
            **bearer(token),
            "Connection": "close, X-Hop",
            "X-Hop": "1",
            "Keep-Alive": "timeout=5",
            "TE": "trailers",
            "Upgrade": "h2c",
            "Proxy-Authorization": "Basic abc",
            "X-Request-Id": "abc",
        },
    )
    sent = upstream[0].headers
    for name in ("x-hop", "keep-alive", "te", "upgrade", "proxy-authorization"):
        assert name not in sent, name
    # Connection ставит сам httpx для своего соединения к сервису
    assert sent["connection"] == "keep-alive"
    assert sent["x-request-id"] == "abc"
    assert sent["authorization"] == f"Bearer {token}"


# --- тело ---


def test_binary_body_passed_unchanged(client, mock_upstream):
    data = bytes(range(256)) * 4
    mock_upstream(
        lambda request: httpx.Response(
            200, headers={"content-type": "application/octet-stream"}, content=data
        )
    )
    r = client.get("/api/tasks/projects", headers=bearer(make_token()))
    assert r.content == data
    assert r.headers["content-length"] == str(len(data))


def test_compressed_body_keeps_content_encoding(client, mock_upstream):
    raw = gzip.compress(b'{"ok": true}')
    mock_upstream(
        lambda request: httpx.Response(200, headers={"content-encoding": "gzip"}, content=raw)
    )
    r = client.get("/api/tasks/projects", headers=bearer(make_token()))
    # клиент получил сжатые байты вместе с заголовком и распаковал их сам
    assert r.headers["content-encoding"] == "gzip"
    assert r.json() == {"ok": True}


async def call_app(path, send):
    """Запрос к ASGI-приложению напрямую: TestClient собирает тело целиком, порядок не виден."""
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"authorization", f"Bearer {make_token()}".encode())],
        "client": ("test", 1),
        "server": ("gateway", 8000),
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    await app(scope, receive, send)


def test_large_body_is_streamed(mock_upstream):
    chunk = bytes(range(256)) * 256  # 64 КиБ
    events = []

    async def upstream_body():
        for i in range(32):
            events.append(("upstream", i))
            yield chunk

    mock_upstream(lambda request: httpx.Response(200, content=upstream_body()))
    received = []

    async def send(message):
        if message["type"] == "http.response.body" and message["body"]:
            events.append(("client", len(received)))
            received.append(message["body"])

    asyncio.run(call_app("/api/tasks/projects", send))
    assert b"".join(received) == chunk * 32
    # первый кусок ушёл клиенту до того, как сервис отдал последний
    assert events.index(("client", 0)) < events.index(("upstream", 31))


@pytest.fixture
def closed_responses(monkeypatch):
    closed = []
    real_aclose = httpx.Response.aclose

    async def spy(self):
        closed.append(self)
        await real_aclose(self)

    monkeypatch.setattr(httpx.Response, "aclose", spy)
    return closed


def test_response_closed_after_body(client, mock_upstream, closed_responses):
    mock_upstream(lambda request: httpx.Response(200, json={}))
    client.get("/api/tasks/projects", headers=bearer(make_token()))
    # aiter_raw закрывает ответ и сам, повторное aclose ничего не делает
    assert len({id(r) for r in closed_responses}) == 1
    assert closed_responses[0].is_closed


def test_response_closed_when_upstream_fails_mid_body(client, mock_upstream, closed_responses):
    async def broken_body():
        yield b"part"
        raise httpx.ReadError("connection reset")

    mock_upstream(lambda request: httpx.Response(200, content=broken_body()))
    # заголовки уже отправлены: ответ обрывается, а не подменяется на 502
    with pytest.raises(httpx.ReadError):
        client.get("/api/tasks/projects", headers=bearer(make_token()))
    assert len(closed_responses) == 1


def test_response_closed_when_client_disconnects(mock_upstream, closed_responses):
    async def body():
        for _ in range(3):
            yield b"a"

    mock_upstream(lambda request: httpx.Response(200, content=body()))

    async def send(message):
        if message["type"] == "http.response.body":
            raise OSError("client gone")

    async def run():
        with pytest.raises(ClientDisconnect):
            await call_app("/api/tasks/projects", send)
        # генератор тела закрывает финализатор asyncio, когда ответ становится мусором
        gc.collect()
        for _ in range(3):
            await asyncio.sleep(0)

    asyncio.run(run())
    assert len(closed_responses) == 1


# --- повтор при обрыве соединения ---


def failing_once(error):
    """Первый запрос обрывается ошибкой error, следующие получают 200; хранит все запросы."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            raise error("connection closed", request=request)
        return httpx.Response(200, json={"ok": True})

    return handler, calls


@pytest.mark.parametrize("method", ["GET", "OPTIONS", "PUT", "DELETE"])
@pytest.mark.parametrize("error", [httpx.RemoteProtocolError, httpx.ReadError, httpx.ConnectError])
def test_idempotent_request_retried_once(client, mock_upstream, method, error):
    handler, calls = failing_once(error)
    mock_upstream(handler)
    r = client.request(
        method, "/api/tasks/projects/1", headers=bearer(make_token()), content=b'{"a":1}'
    )
    assert r.status_code == 200
    assert len(calls) == 2
    assert calls[1].content == b'{"a":1}'


@pytest.mark.parametrize("method", ["POST", "PATCH"])
def test_non_idempotent_request_not_retried(client, mock_upstream, method):
    handler, calls = failing_once(httpx.RemoteProtocolError)
    mock_upstream(handler)
    r = client.request(method, "/api/tasks/projects", headers=bearer(make_token()), content=b"{}")
    assert r.status_code == 502
    assert len(calls) == 1


def test_retry_failure_returns_502(client, mock_upstream):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.RemoteProtocolError("connection closed", request=request)

    mock_upstream(handler)
    r = client.get("/api/tasks/projects", headers=bearer(make_token()))
    assert r.status_code == 502
    assert len(calls) == 2


def test_timeout_not_retried(client, mock_upstream):
    handler, calls = failing_once(httpx.ReadTimeout)
    mock_upstream(handler)
    r = client.get("/api/tasks/projects", headers=bearer(make_token()))
    assert r.status_code == 504
    assert len(calls) == 1
