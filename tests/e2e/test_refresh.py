"""Авто-refresh токена во фронте (frontend/login_page/src/services/api.ts).

На 401 (кроме login/register/refresh) интерцептор делает один общий POST /api/auth/refresh на все
параллельные запросы (refreshPromise) и повторяет их; неудачный refresh удаляет токены
и уводит на /login.
При перезагрузке /dashboard запросы идут параллельно: GET /api/auth/me из стора и из onMounted —
так проверяется именно общий промис, а не один запрос.
"""

import re

from playwright.sync_api import expect

from helpers import USER1, local_storage, login

REFRESH = ("POST", "/api/auth/refresh")


def test_expired_access_token_refreshed_once(open_session, base_url):
    s = open_session()
    login(s.page, USER1)
    refresh_token = local_storage(s.page, "refresh_token")

    s.page.evaluate("localStorage.setItem('access_token', 'abc')")
    s.net.clear()
    with s.page.expect_response(
        lambda r: r.request.method == REFRESH[0] and r.url.endswith(REFRESH[1])
    ):
        s.page.reload()
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
