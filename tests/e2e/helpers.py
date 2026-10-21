"""Помощники e2e: seed-пользователи, таймауты, вход через UI, запись сетевых событий страницы.

Seed-пользователи — те же, что в tests/smoke.sh: admin, user1, user2 @example.com,
пароль password123.
"""

import re
from dataclasses import dataclass, field
from typing import Self
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import BrowserContext, Page, Response, expect

PASSWORD = "password123"
ADMIN = "admin@example.com"
USER1 = "user1@example.com"
USER2 = "user2@example.com"

# С запасом на нагруженный узел: у admin дашборд грузит задачи по каждому проекту последовательно.
# Ожидания — только по событиям, без фиксированных пауз.
TIMEOUT_MS = 20_000
NAVIGATION_TIMEOUT_MS = 30_000
expect.set_options(timeout=TIMEOUT_MS)


def origin(url: str) -> str:
    u = urlsplit(url)
    return f"{u.scheme}://{u.netloc}"


def api_path(url: str) -> str:
    return urlsplit(url).path


@dataclass
class Net:
    """Запросы и ответы страницы в порядке прихода.

    В sync API обработчики событий вызываются только внутри вызовов Playwright (goto, expect,
    wait_for_*), поэтому после действия нужно дождаться события Playwright, а не time.sleep.
    """

    requests: list[str] = field(default_factory=list)
    responses: list[tuple[str, str, int]] = field(default_factory=list)  # (метод, путь, код)

    def attach(self, page: Page) -> Self:
        page.on("request", lambda r: self.requests.append(r.url))
        page.on("response", self._on_response)
        return self

    def _on_response(self, r: Response) -> None:
        if api_path(r.url).startswith("/api/"):
            self.responses.append((r.request.method, api_path(r.url), r.status))

    def clear(self) -> None:
        self.requests.clear()
        self.responses.clear()

    def api(self, method: str, path: str) -> list[int]:
        return [s for m, p, s in self.responses if m == method and p == path]

    def foreign(self, base_url: str) -> list[str]:
        """Запросы не на origin фронта (data: и blob: не считаются — это не сеть)."""
        own = origin(base_url)
        return [
            u for u in self.requests if not u.startswith(("data:", "blob:")) and origin(u) != own
        ]


@dataclass
class Session:
    context: BrowserContext
    page: Page
    net: Net


def is_projects_list(r: Response) -> bool:
    return r.request.method == "GET" and api_path(r.url) == "/api/tasks/projects"


def login(page: Page, email: str) -> list[dict]:
    """Вход через форму; возвращает тело GET /api/tasks/projects — список, загруженный дашбордом.

    Возвращает управление, когда дашборд догрузился: после списка проектов он по одному запрашивает
    задачи каждого проекта (GET /api/tasks/tasks?project_id=N). Без этого ожидания тест ловит хвост
    этих запросов (1.5.6: ответ старой страницы попадал в лог после reload, а подменённый токен —
    в её запрос). wait_for_load_state("networkidle") тут не годится: переход /login -> /dashboard —
    это pushState без новой загрузки документа, и состояние считается уже достигнутым.
    """
    loaded: set[int] = set()

    def on_response(r: Response) -> None:
        if r.request.method == "GET" and api_path(r.url) == "/api/tasks/tasks":
            ids = parse_qs(urlsplit(r.url).query).get("project_id", [])
            loaded.update(int(i) for i in ids)

    page.on("response", on_response)
    page.goto("/login")
    page.get_by_placeholder("your@email.com").fill(email)
    page.get_by_placeholder("••••••••").fill(PASSWORD)
    with page.expect_response(is_projects_list) as projects:
        page.get_by_role("button", name="Войти").click()
    expect(page).to_have_url(re.compile(r"/dashboard$"))
    status = projects.value.status
    assert status == 200, f"GET /api/tasks/projects после входа {email}: {status}"
    body = projects.value.json()
    # обработчики sync API вызываются внутри вызовов Playwright: ждём следующий ответ, пока
    # не придут задачи всех проектов (нет нужного ответа за TIMEOUT_MS — ошибка таймаута)
    while not {p["id"] for p in body} <= loaded:
        page.wait_for_event("response")
    page.remove_listener("response", on_response)
    return body


def local_storage(page: Page, key: str) -> str | None:
    return page.evaluate("k => localStorage.getItem(k)", key)
