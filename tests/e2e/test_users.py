"""Страница пользователей /users: только admin; отключение и включение пользователя.

Seed-пользователей тест не трогает (на них опираются остальные тесты и smoke): отключается
пользователь, которого тест сам регистрирует через API.
"""

import re

from playwright.sync_api import expect

from helpers import ADMIN, PASSWORD, USER1, api_path, login


def test_user_cannot_open_users_page(open_session, base_url):
    s = open_session()
    login(s.page, USER1)
    expect(s.page.get_by_role("button", name="Пользователи")).to_have_count(0)

    s.net.clear()
    s.page.goto("/users")
    expect(s.page).to_have_url(re.compile(r"/dashboard$"))
    assert s.net.api("GET", "/api/auth/users") == [], "user запросил список пользователей"
    assert s.net.foreign(base_url) == [], "запросы не на origin фронта"


def test_admin_disables_and_enables_user(open_session, base_url, run_label):
    email = f"{run_label}@example.com"
    s = open_session()
    registered = s.page.request.post(
        "/api/auth/register", data={"email": email, "password": PASSWORD}
    )
    assert registered.status == 201, f"регистрация {email}: {registered.status}"

    def login_status() -> int:
        return s.page.request.post(
            "/api/auth/login", data={"email": email, "password": PASSWORD}
        ).status

    assert login_status() == 200, "новый пользователь не вошёл до отключения"

    login(s.page, ADMIN)
    s.page.get_by_role("button", name="Пользователи").click()
    expect(s.page).to_have_url(re.compile(r"/users$"))

    # поиск находит ровно пользователя теста
    s.page.get_by_placeholder("Поиск по email или имени").fill(email)
    row = s.page.locator(".user-row").filter(has_text=email)
    expect(row).to_have_count(1)
    expect(s.page.locator(".user-row")).to_have_count(1)

    def is_patch(r) -> bool:
        return r.request.method == "PATCH" and api_path(r.url).startswith("/api/auth/users/")

    with s.page.expect_response(is_patch) as disabled:
        row.get_by_role("button", name="Отключить").click()
    assert disabled.value.status == 200, f"отключение: {disabled.value.status}"
    assert disabled.value.json()["is_active"] is False
    expect(row.get_by_role("button", name="Включить")).to_have_count(1)
    assert login_status() == 403, "отключённый пользователь вошёл"

    with s.page.expect_response(is_patch) as enabled:
        row.get_by_role("button", name="Включить").click()
    assert enabled.value.status == 200, f"включение: {enabled.value.status}"
    expect(row.get_by_role("button", name="Отключить")).to_have_count(1)
    assert login_status() == 200, "включённый пользователь не вошёл"

    # у своей строки действий нет
    s.page.get_by_placeholder("Поиск по email или имени").fill(ADMIN)
    own = s.page.locator(".user-row").filter(has_text=ADMIN)
    expect(own).to_have_count(1)
    expect(own.get_by_role("button")).to_have_count(0)
    assert s.net.foreign(base_url) == [], "запросы не на origin фронта"
