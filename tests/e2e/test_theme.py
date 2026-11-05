"""Тема: выбор в шапке переживает перезагрузку, «Как в системе» идёт за темой браузера.

Выбор хранится в localStorage («theme», stores/theme.ts). Inline-скрипт index.html ставит
data-theme у <html> до загрузки JS — без него при открытии мелькала бы светлая тема; тест проверяет
его отдельно, со страницей без JS. Переключатель на компьютере — три кнопки с aria-pressed
(до 960 px они в списке под значком, а e2e идут в окне 1280 × 720).
"""

import re

from playwright.sync_api import expect

from helpers import USER1, local_storage, login


def test_theme_choice_persists_and_follows_system(open_session, base_url):
    # браузер со светлой темой: по умолчанию «Как в системе» → светлая
    s = open_session()
    login(s.page, USER1)
    html = s.page.locator("html")
    expect(html).to_have_attribute("data-theme", "light")
    expect(s.page.get_by_role("button", name="Как в системе")).to_have_attribute(
        "aria-pressed", "true"
    )

    dark = s.page.get_by_role("button", name="Тёмная")
    dark.click()
    expect(dark).to_have_attribute("aria-pressed", "true")
    expect(html).to_have_attribute("data-theme", "dark")
    assert local_storage(s.page, "theme") == "dark"

    # после перезагрузки тема и выбор те же
    s.page.reload()
    expect(s.page).to_have_url(re.compile(r"/dashboard$"))
    expect(html).to_have_attribute("data-theme", "dark")
    expect(dark).to_have_attribute("aria-pressed", "true")

    # тему до загрузки JS ставит inline-скрипт: JS-чанки не грузятся, data-theme всё равно dark
    no_js = s.context.new_page()
    no_js.route(re.compile(r"/assets/.*\.js$"), lambda route: route.abort())
    no_js.goto("/dashboard")
    expect(no_js.locator("html")).to_have_attribute("data-theme", "dark")
    no_js.close()

    # «Как в системе» следит за темой браузера на лету
    s.page.get_by_role("button", name="Как в системе").click()
    expect(html).to_have_attribute("data-theme", "light")
    s.page.emulate_media(color_scheme="dark")
    expect(html).to_have_attribute("data-theme", "dark")

    # новый браузер с тёмной темой, выбора нет: тёмная сразу (вход не нужен)
    guest = open_session(color_scheme="dark")
    guest.page.goto("/login")
    expect(guest.page.locator("html")).to_have_attribute("data-theme", "dark")
    assert local_storage(guest.page, "theme") is None

    for sess in (s, guest):
        assert sess.net.foreign(base_url) == [], "запросы не на origin фронта"
