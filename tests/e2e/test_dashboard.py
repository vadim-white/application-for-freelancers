"""Дашборд: счётчик задач в карточке проекта и стартовый роут `/`.

Карточка показывает первые три задачи, а счётчик «(N)» — по всем активным задачам проекта.
Превью и счётчик приходят в ответе списка проектов: дашборд не запрашивает задачи по проектам.
`/` ведёт залогиненного на /dashboard, остальных на /login; /login и /register залогиненного —
на /dashboard (frontend/login_page/src/router/index.ts).
"""

import re

from playwright.sync_api import expect

from helpers import USER1, local_storage, login

TASKS = 4


def test_project_card_counts_all_tasks(open_session, base_url, run_label):
    s = open_session()
    login(s.page, USER1)
    headers = {"Authorization": f"Bearer {local_storage(s.page, 'access_token')}"}

    name = f"{run_label} счётчик"
    created = s.page.request.post("/api/tasks/projects", headers=headers, data={"name": name})
    assert created.status == 201, f"создание проекта: {created.status}"
    project_id = created.json()["id"]
    for i in range(TASKS):
        r = s.page.request.post(
            "/api/tasks/tasks",
            headers=headers,
            data={"title": f"{run_label} задача {i + 1}", "project_id": project_id},
        )
        assert r.status == 201, f"создание задачи {i + 1}: {r.status}"

    # дашборд грузит проекты при открытии — перезагрузка подхватывает созданное
    s.page.reload()
    card = s.page.locator(".project-card").filter(has_text=name)
    expect(card).to_have_count(1)
    expect(card.locator(".task-count")).to_have_text(f"({TASKS})")
    expect(card.locator(".task-item")).to_have_count(3)
    # вход и перезагрузка: список проектов есть, запросов задач нет
    assert s.net.api("GET", "/api/tasks/projects") == [200, 200]
    assert s.net.api("GET", "/api/tasks/tasks") == [], "дашборд запросил задачи по проектам"
    assert s.net.foreign(base_url) == [], "запросы не на origin фронта"


def test_root_route_by_auth_state(open_session, base_url):
    # без входа: / -> /login, /dashboard -> /login
    guest = open_session()
    guest.page.goto("/")
    expect(guest.page).to_have_url(re.compile(r"/login$"))

    # со входом: / -> /dashboard, /login и /register -> /dashboard
    s = open_session()
    login(s.page, USER1)
    for path in ("/", "/login", "/register"):
        s.page.goto(path)
        expect(s.page).to_have_url(re.compile(r"/dashboard$"))
        expect(s.page.locator(".dashboard-header")).to_be_visible()
    for sess in (guest, s):
        assert sess.net.foreign(base_url) == [], "запросы не на origin фронта"
