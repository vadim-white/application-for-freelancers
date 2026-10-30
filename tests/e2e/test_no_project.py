"""Задачи вне проекта: карточка «Без проекта» и её панель.

NoProjectCard.vue и ProjectTasksDrawer.vue в frontend/login_page/src.

Карточка первая на дашборде, у неё свой класс `.no-project-card` (не `.project-card`: тот считает
`login()`). Панель — та же, что у проекта, с `project_id=none`. Задачи копятся у user1 между
прогонами, поэтому проверки — по названию внутри панели (сортировка «новые сверху») и по счётчику
«до → после» (до — из API), а не «первая в списке».
"""

from playwright.sync_api import Page, expect

from helpers import ADMIN, USER1, local_storage, login, wait_responses
from test_edit import choose, is_patch, open_task_edit, prepare, sent

TASKS = "/api/tasks/tasks"
NONE_ACTIVE = {"project_id": "none", "is_active": "true", "limit": "1"}


def headers_of(page: Page) -> dict:
    return {"Authorization": f"Bearer {local_storage(page, 'access_token')}"}


def no_project_total(page: Page) -> int:
    """Число активных задач вне проекта, которые видит этот пользователь."""
    r = page.request.get(TASKS, headers=headers_of(page), params=NONE_ACTIVE)
    assert r.status == 200, f"список задач вне проекта: {r.status}"
    return r.json()["total"]


def open_panel(page: Page) -> None:
    page.locator(".no-project-card").click()
    expect(page.locator(".n-drawer .drawer-title")).to_have_text("Без проекта")
    choose(page, ".n-drawer .task-sort", "Создана ↓")


def add_task(page: Page, title: str) -> dict:
    """Добавляет задачу в открытой панели; возвращает ответ POST и тело запроса."""
    page.get_by_placeholder("Введите название задачи...").fill(title)
    with page.expect_response(lambda r: r.request.method == "POST" and r.url.endswith(TASKS)) as r:
        page.get_by_role("button", name="Добавить задачу").click()
    assert r.value.status == 201, f"создание задачи вне проекта: {r.value.status}"
    assert "project_id" not in sent(r.value), sent(r.value)
    return r.value.json()


def test_create_task_without_project(open_session, base_url, run_label):
    u1 = open_session()
    login(u1.page, USER1)
    page, headers = u1.page, headers_of(u1.page)
    # дашборд при входе уже запросил задачи вне проекта
    wait_responses(u1, "GET", TASKS, 1)
    assert u1.net.api("GET", TASKS) == [200]
    # архивная задача вне проекта в счётчик не входит
    archived = page.request.post(TASKS, headers=headers, data={"title": f"{run_label} архив"})
    assert archived.status == 201, f"создание задачи: {archived.status}"
    r = page.request.patch(
        f"{TASKS}/{archived.json()['id']}", headers=headers, data={"is_active": False}
    )
    assert r.status == 200, f"архивация: {r.status}"
    before = no_project_total(page)
    title = f"{run_label} вне проекта"

    open_panel(page)
    created = add_task(page, title)
    assert created["project_id"] is None
    row = page.locator(".n-drawer .task-item").filter(has_text=title)
    expect(row).to_have_count(1)
    # карточка перечитана: счётчик «до → после»
    expect(page.locator(".no-project-card .task-count")).to_have_text(f"({before + 1})")
    api_task = page.request.get(f"{TASKS}/{created['id']}", headers=headers).json()
    assert api_task["project_id"] is None

    # таймер на задаче вне проекта стартует
    row.get_by_role("button", name="Открыть таймер").click()
    try:
        with page.expect_response(
            lambda r: r.request.method == "POST" and r.url.endswith("/api/time/timer/start")
        ) as started:
            page.locator(".timer-modal").get_by_role("button", name="Старт").click()
        assert started.value.status == 201, f"старт таймера: {started.value.status}"
        assert started.value.json()["entry"]["task_id"] == created["id"]
    finally:
        stopped = page.request.post("/api/time/timer/stop", headers=headers)
        assert stopped.status == 200, f"остановка таймера: {stopped.status}"

    # admin видит ту же панель с задачами всех, а своя задача у него — своя
    adm = open_session()
    login(adm.page, ADMIN)
    open_panel(adm.page)
    expect(adm.page.locator(".n-drawer .task-item").filter(has_text=title)).to_have_count(1)
    admin_title = f"{run_label} вне проекта admin"
    admin_total = no_project_total(adm.page)
    admin_task = add_task(adm.page, admin_title)
    assert admin_task["project_id"] is None
    assert admin_task["owner_id"] != api_task["owner_id"], "задача admin записана на user1"
    expect(adm.page.locator(".no-project-card .task-count")).to_have_text(f"({admin_total + 1})")
    for s in (u1, adm):
        assert s.net.foreign(base_url) == [], "запросы не на origin фронта"


def test_move_task_out_of_project(open_session, base_url, run_label):
    s = open_session()
    title = f"{run_label} вынос"
    name = f"{run_label} вынос проект"
    headers, _, task_id = prepare(s, [name], title)
    page = s.page
    path = f"{TASKS}/{task_id}"
    before = no_project_total(page)
    card = page.locator(".project-card").filter(has_text=name)
    expect(card.locator(".task-item")).to_have_count(1)
    card.click()

    row, modal = open_task_edit(page, title)
    choose(page, ".task-edit-project", "Без проекта")
    with page.expect_response(is_patch(path)) as saved:
        modal.get_by_role("button", name="Сохранить").click()
    assert saved.value.status == 200, f"вынос: {saved.value.status}"
    assert sent(saved.value) == {"project_id": None}, sent(saved.value)
    # из панели проекта пропала, карточки перечитаны
    expect(row).to_have_count(0)
    expect(card.locator(".task-item")).to_have_count(0)
    expect(page.locator(".no-project-card .task-count")).to_have_text(f"({before + 1})")
    assert page.request.get(path, headers=headers).json()["project_id"] is None

    # в «Без проекта» появилась; в окне правки там выбран «Без проекта»
    page.keyboard.press("Escape")
    expect(page.locator(".n-drawer")).to_be_hidden()
    open_panel(page)
    _, modal = open_task_edit(page, title)
    expect(page.locator(".task-edit-project")).to_contain_text("Без проекта")
    assert s.net.foreign(base_url) == [], "запросы не на origin фронта"
