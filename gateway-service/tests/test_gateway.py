from datetime import timedelta

import httpx
import pytest

from app import health, proxy
from app.core.config import settings
from tests.conftest import bearer, make_token


# --- публичные пути ---

@pytest.mark.parametrize("path", ["/api/auth/login", "/api/auth/register", "/api/auth/refresh"])
def test_public_auth_endpoints_without_token(client, upstream, path):
    r = client.post(path, json={})
    assert r.status_code == 200
    assert str(upstream[0].url) == "http://auth" + path


def test_root_and_health_without_token(client, upstream):
    assert client.get("/").status_code == 200
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["upstreams"] == {"auth": True, "task": True, "time": True}


def mock_httpx(monkeypatch, module, handler):
    """Подменяет транспорт httpx.AsyncClient в module (health или proxy)."""
    real_client = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(module.httpx, "AsyncClient", fake_client)


def test_health_upstream_unreachable_or_not_200(client, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "auth":
            raise httpx.ConnectError("connection refused", request=request)
        if request.url.host == "task":
            return httpx.Response(503)
        return httpx.Response(200)

    mock_httpx(monkeypatch, health, handler)
    r = client.get("/health")
    # сам /health отвечает 200 всегда: состояние сервисов — только в теле
    assert r.status_code == 200
    assert r.json() == {"gateway": "ok", "upstreams": {"auth": False, "task": False, "time": True}}


def test_health_all_upstreams_down(client, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout", request=request)

    mock_httpx(monkeypatch, health, handler)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["upstreams"] == {"auth": False, "task": False, "time": False}


# --- 401 ---

@pytest.mark.parametrize("path", [
    "/api/auth/me",
    "/api/tasks/projects",
    "/api/time/time-entries",
    "/api/tasks/statistics/users",
    "/api/auth/login/",  # не точное совпадение с публичным путём
])
def test_protected_without_token_returns_401(client, upstream, path):
    r = client.get(path)
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"
    assert upstream == []


@pytest.mark.parametrize("header", [
    "Basic abc",
    "Bearer",
    "Bearer a b",
    "Bearer not-a-jwt",
])
def test_malformed_authorization_returns_401(client, upstream, header):
    r = client.get("/api/tasks/projects", headers={"Authorization": header})
    assert r.status_code == 401
    assert upstream == []


@pytest.mark.parametrize("token", [
    make_token(expires_in=timedelta(seconds=-10)),       # просрочен
    make_token(expires_in=None),                         # без exp
    make_token(secret="other-secret"),                   # чужая подпись
    make_token(token_type="refresh"),                    # refresh вместо access
    make_token(token_type=None),                         # без type
    make_token(sub=None),                                # без sub
    make_token(sub="abc"),                               # sub не число
    make_token(role="superuser"),                        # неизвестная роль
], ids=["expired", "no-exp", "bad-signature", "refresh", "no-type", "no-sub", "bad-sub", "bad-role"])
def test_invalid_tokens_return_401(client, upstream, token):
    r = client.get("/api/tasks/projects", headers=bearer(token))
    assert r.status_code == 401
    assert upstream == []


def test_alg_none_token_rejected(client, upstream):
    import base64, json
    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    token = b64({"alg": "none", "typ": "JWT"}) + "." + b64({"sub": "1", "type": "access", "role": "admin", "exp": 9999999999}) + "."
    r = client.get("/api/tasks/projects", headers=bearer(token))
    assert r.status_code == 401
    assert upstream == []


# --- 404 ---

@pytest.mark.parametrize("path", [
    "/api/unknown",
    "/api/authx/login",
    "/api/",
    "/api/tasks/%2e%2e/auth/me",
    "/api/auth/login/%2E%2E/%2E%2E/tasks/projects",
])
def test_unknown_paths_return_404(client, upstream, path):
    r = client.get(path, headers=bearer(make_token()))
    assert r.status_code == 404
    assert upstream == []


@pytest.mark.parametrize("path", [
    "/api/tasks/../auth/me",
    "/api/auth/login/../../tasks/projects",
    "/api/time/./time-entries",
])
def test_resolve_upstream_rejects_dot_segments(path):
    from app.proxy import resolve_upstream
    assert resolve_upstream(path) is None


# --- маршрутизация и заголовки ---

@pytest.mark.parametrize("path, target", [
    ("/api/auth/me", "http://auth/api/auth/me"),
    ("/api/tasks/tasks?project_id=3", "http://task/api/tasks/tasks?project_id=3"),
    ("/api/time/time-entries", "http://time/api/time/time-entries"),
])
def test_valid_token_routes_to_service(client, upstream, path, target):
    r = client.get(path, headers=bearer(make_token()))
    assert r.status_code == 200
    assert str(upstream[0].url) == target


def test_sets_user_headers_from_token(client, upstream):
    token = make_token(sub="42", role="admin")
    client.get("/api/tasks/projects", headers=bearer(token))
    sent = upstream[0].headers
    assert sent["x-user-id"] == "42"
    assert sent["x-user-role"] == "admin"
    # сервисы проверяют токен сами, поэтому Authorization пробрасывается
    assert sent["authorization"] == f"Bearer {token}"


def test_overwrites_client_user_headers(client, upstream):
    headers = {
        **bearer(make_token(sub="7", role="user")),
        "X-User-Id": "1",
        "X-User-Role": "admin",
        "X-User-Email": "admin@example.com",
    }
    client.get("/api/time/time-entries", headers=headers)
    sent = upstream[0].headers
    assert sent.get_list("x-user-id") == ["7"]
    assert sent.get_list("x-user-role") == ["user"]
    assert "x-user-email" not in sent


def test_strips_client_user_headers_on_public_path(client, upstream):
    client.post("/api/auth/login", json={}, headers={"X-User-Id": "1", "X-User-Role": "admin"})
    sent = upstream[0].headers
    assert "x-user-id" not in sent
    assert "x-user-role" not in sent


def test_missing_role_defaults_to_user(client, upstream):
    # токены после /refresh пока без role
    client.get("/api/tasks/projects", headers=bearer(make_token(role=None)))
    assert upstream[0].headers["x-user-role"] == "user"


def test_forwards_method_and_body(client, upstream):
    r = client.post("/api/tasks/tasks", json={"title": "t"}, headers=bearer(make_token()))
    assert r.status_code == 200
    req = upstream[0]
    assert req.method == "POST"
    assert req.content == b'{"title":"t"}'


def test_body_without_content_type_defaults_to_json(client, upstream):
    r = client.post("/api/tasks/tasks", content=b'{"title":"t"}', headers=bearer(make_token()))
    assert r.status_code == 200
    assert upstream[0].headers["content-type"] == "application/json"


@pytest.mark.parametrize("error", [httpx.ConnectError, httpx.ReadTimeout])
def test_upstream_unavailable_returns_502(client, monkeypatch, error):
    def handler(request: httpx.Request) -> httpx.Response:
        raise error("upstream down", request=request)

    mock_httpx(monkeypatch, proxy, handler)
    r = client.get("/api/tasks/projects", headers=bearer(make_token()))
    assert r.status_code == 502
    assert r.text == "Upstream service unavailable"


def test_upstream_error_status_is_passed_through(client, monkeypatch):
    mock_httpx(monkeypatch, proxy, lambda request: httpx.Response(404, json={"detail": "Not found"}))
    r = client.get("/api/tasks/projects/9", headers=bearer(make_token()))
    assert r.status_code == 404
    assert r.json() == {"detail": "Not found"}


def test_cors_preflight_without_token(client, upstream):
    r = client.options("/api/tasks/projects", headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "authorization",
    })
    assert r.status_code == 200
    assert upstream == []


def preflight(client, origin):
    return client.options("/api/tasks/projects", headers={
        "Origin": origin,
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "authorization",
    })


def test_cors_origins_parsed_from_env():
    assert settings.cors_origins == ["http://localhost:5173", "http://app.example"]


@pytest.mark.parametrize("origin", ["http://localhost:5173", "http://app.example"])
def test_cors_allowed_origin(client, upstream, origin):
    r = preflight(client, origin)
    assert r.headers["access-control-allow-origin"] == origin
    assert "access-control-allow-credentials" not in r.headers


def test_cors_foreign_origin_rejected(client, upstream):
    r = preflight(client, "http://evil.example")
    assert r.status_code == 400
    assert "access-control-allow-origin" not in r.headers
    assert upstream == []


def test_cors_no_wildcard_on_simple_request(client, upstream):
    r = client.get("/", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in r.headers


def test_cors_headers_on_401(client, upstream):
    # фронт должен видеть 401, чтобы обновить токен
    r = client.get("/api/tasks/tasks", headers={"Origin": "http://localhost:5173"})
    assert r.status_code == 401
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"

