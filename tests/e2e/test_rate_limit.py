"""429 на входе: сообщение на странице входа (счётчик неудачных входов auth, G2).

Запирается только пользователь, которого тест сам регистрирует: seed-пользователей на счётчик
не ставим (на них опираются остальные тесты и smoke).
"""

import re

from playwright.sync_api import expect

from helpers import PASSWORD


def test_login_form_shows_too_many_attempts(open_session, base_url, run_label):
    email = f"{run_label}-lock@example.com"
    s = open_session()
    registered = s.page.request.post(
        "/api/auth/register", data={"email": email, "password": PASSWORD}
    )
    assert registered.status == 201, f"регистрация {email}: {registered.status}"

    # пять неверных входов исчерпывают окно: шестая попытка (ниже, через форму) получает 429
    for i in range(5):
        wrong = s.page.request.post(
            "/api/auth/login", data={"email": email, "password": "wrong-password"}
        )
        assert wrong.status == 401, f"неверный вход {i + 1}: {wrong.status}"

    s.page.goto("/login")
    s.page.get_by_placeholder("your@email.com").fill(email)
    s.page.get_by_placeholder("••••••••").fill(PASSWORD)
    s.net.clear()
    with s.page.expect_response(
        lambda r: r.request.method == "POST" and r.url.endswith("/api/auth/login")
    ) as resp:
        s.page.get_by_role("button", name="Войти").click()
    assert resp.value.status == 429, f"вход через форму: {resp.value.status}"

    expect(s.page.get_by_text("Слишком много попыток входа")).to_be_visible()
    expect(s.page).to_have_url(re.compile(r"/login$"))
    assert s.net.foreign(base_url) == [], "запросы не на origin фронта"
