"""Авто-refresh токена во фронте (frontend/login_page/src/services/api.ts).

На 401 (кроме login/register/refresh) интерцептор делает один общий POST /api/auth/refresh на все
параллельные запросы (refreshPromise) и повторяет их; неудачный refresh удаляет токены
и уводит на /login; 429 на refresh (лимит входа) сессию не завершает.
При перезагрузке /dashboard GET /api/auth/me идёт из стора и из onMounted дашборда. Дашборд —
ленивый чанк, и без задержки второй запрос мог уйти и до, и во время, и после refresh (зависит от
скорости машины), поэтому тест держит ответ refresh, пока оба запроса не получат 401: так
проверяется именно общий промис, а не один запрос.
"""

import re

from playwright.sync_api import expect

from helpers import USER1, local_storage, login, wait_responses

REFRESH = ("POST", "/api/auth/refresh")


def test_expired_access_token_refreshed_once(open_session, base_url):
    s = open_session()
    login(s.page, USER1)
    refresh_token = local_storage(s.page, "refresh_token")

    s.page.evaluate("localStorage.setItem('access_token', 'abc')")
    s.net.clear()
    held = []
    s.page.route("**/api/auth/refresh", lambda route: held.append(route))
    s.page.reload()
    wait_responses(s, "GET", "/api/auth/me", 2)
    assert len(held) == 1, f"refresh до двух 401: {len(held)}; ответы API: {s.net.responses}"
    with s.page.expect_response(
        lambda r: r.request.method == REFRESH[0] and r.url.endswith(REFRESH[1])
    ):
        held[0].continue_()
    s.page.unroute("**/api/auth/refresh")
    # повторы после refresh и загрузка проектов — дождаться, пока сеть затихнет
    s.page.wait_for_load_state("networkidle")

    log = s.net.responses
    refreshes = s.net.api(*REFRESH)
    assert refreshes == [200], (
        f"ожидался ровно один POST /api/auth/refresh с 200, получено {refreshes}; ответы API: {log}"
    )
    failed = [(m, p) for m, p, st in log if st == 401]
    assert len(failed) >= 2, (
        f"ожидалось не меньше двух параллельных 401 (проверка общего refresh), получено {failed}; "
        f"ответы API: {log}"
    )
    i_refresh = log.index((*REFRESH, 200))
    for m, p, st in log[:i_refresh]:
        assert st == 401, f"до refresh пришёл ответ {m} {p} {st}, ожидались только 401; {log}"
    for m, p in failed:
        assert (m, p, 200) in log[i_refresh + 1 :], (
            f"{m} {p} не повторён с 200 после refresh; {log}"
        )
    assert all(st == 200 for _, _, st in log[i_refresh + 1 :]), f"после refresh не все 200: {log}"

    expect(s.page).to_have_url(re.compile(r"/dashboard$"))
    new_access = local_storage(s.page, "access_token")
    assert new_access not in (None, "abc"), f"access_token после refresh: {new_access!r}"
    assert local_storage(s.page, "refresh_token") == refresh_token
    assert s.net.foreign(base_url) == [], "запросы не на origin фронта"


def test_failed_refresh_logs_out(open_session, base_url):
    s = open_session()
    login(s.page, USER1)

    s.page.evaluate(
        "localStorage.setItem('access_token', 'abc'); localStorage.setItem('refresh_token', 'abc')"
    )
    s.net.clear()
    with s.page.expect_response(
        lambda r: r.request.method == REFRESH[0] and r.url.endswith(REFRESH[1])
    ):
        s.page.reload()
    expect(s.page).to_have_url(re.compile(r"/login$"))
    s.page.wait_for_load_state("networkidle")

    refreshes = s.net.api(*REFRESH)
    assert refreshes == [401], (
        f"ожидался ровно один POST /api/auth/refresh с 401, получено {refreshes}; "
        f"ответы API: {s.net.responses}"
    )
    assert local_storage(s.page, "access_token") is None
    assert local_storage(s.page, "refresh_token") is None
    expect(s.page.get_by_role("button", name="Войти")).to_be_visible()
    assert s.net.foreign(base_url) == [], "запросы не на origin фронта"


def test_refresh_429_keeps_session(open_session, base_url):
    """Настоящий 429 на refresh — залп больше 10/с, общий лимит со smoke и e2e; ответ подменён."""
    s = open_session()
    login(s.page, USER1)
    refresh_token = local_storage(s.page, "refresh_token")

    s.page.route(
        "**/api/auth/refresh",
        lambda route: route.fulfill(status=429, headers={"Retry-After": "1"}, body="Too Many"),
    )
    s.page.evaluate("localStorage.setItem('access_token', 'abc')")
    s.net.clear()
    with s.page.expect_response(
        lambda r: r.request.method == REFRESH[0] and r.url.endswith(REFRESH[1])
    ):
        s.page.reload()
    s.page.wait_for_load_state("networkidle")

    # запросы, получившие 401 позже, делают новый refresh (общий промис живёт до ответа)
    refreshes = s.net.api(*REFRESH)
    assert refreshes and set(refreshes) == {429}, f"ответы API: {s.net.responses}"
    expect(s.page).to_have_url(re.compile(r"/dashboard$"))
    assert local_storage(s.page, "access_token") == "abc"
    assert local_storage(s.page, "refresh_token") == refresh_token
    assert s.net.foreign(base_url) == [], "запросы не на origin фронта"
