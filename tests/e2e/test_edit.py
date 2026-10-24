"""Окна правки задачи и проекта (frontend/login_page/src: TaskEditModal.vue, ProjectEditModal.vue).

«Изменить» есть у каждой задачи в панели и на карточке проекта. На `PATCH` уходят только изменённые
поля, очищенное поле — `null`, без изменений запроса нет. Объекты создаются через API: тест
проверяет окна, а не формы создания.
"""

import re

from playwright.sync_api import Page, Response, expect

from helpers import ADMIN, USER1, USER2, Session, api_path, local_storage, login

TASK_DESCRIPTION = "описание до правки"
DEADLINE_TEXT = "2030-05-17 10:30:00"


def prepare(s: Session, names: list[str], title: str) -> tuple[dict, list[int], int]:
    """Вход user1, проекты с этими именами, задача `title` в первом (пустое — без задачи)."""
    login(s.page, USER1)
    headers = {"Authorization": f"Bearer {local_storage(s.page, 'access_token')}"}
    project_ids = []
    for name in names:
        r = s.page.request.post("/api/tasks/projects", headers=headers, data={"name": name})
        assert r.status == 201, f"создание проекта {name}: {r.status}"
        project_ids.append(r.json()["id"])
    task_id = 0
    if title:
        r = s.page.request.post(
            "/api/tasks/tasks",
            headers=headers,
            data={"title": title, "description": TASK_DESCRIPTION, "project_id": project_ids[0]},
        )
        assert r.status == 201, f"создание задачи: {r.status}"
        task_id = r.json()["id"]
    # дашборд грузит проекты при открытии — перезагрузка подхватывает созданное
    s.page.reload()
    return headers, project_ids, task_id


def choose(page: Page, select: str, label: str) -> None:
    page.locator(select).click()
    page.locator(".n-base-select-option").filter(has_text=label).click()


def is_patch(path: str):
    return lambda r: r.request.method == "PATCH" and api_path(r.url) == path


def sent(response: Response) -> dict:
    """Тело запроса, на который пришёл ответ."""
    return response.request.post_data_json


def open_task_edit(page: Page, title: str):
    row = page.locator(".n-drawer .task-item").filter(has_text=title)
    row.get_by_role("button", name="Изменить").click()
    modal = page.locator(".task-edit-modal")
    expect(modal.locator(".task-edit-title input")).to_have_value(title)
    return row, modal


def test_task_edit_fields(open_session, base_url, run_label):
    s = open_session()
    title = f"{run_label} правка задачи"
    new_title = f"{run_label} правка задачи (новая)"
    headers, _, task_id = prepare(s, [f"{run_label} правка"], title)
    page = s.page
    path = f"/api/tasks/tasks/{task_id}"
    # таймер на этой задаче: после переименования индикатор покажет новое название
    started = page.request.post("/api/time/timer/start", headers=headers, data={"task_id": task_id})
    assert started.status == 201, f"старт таймера: {started.status}"
    try:
        page.reload()
        page.locator(".project-card").filter(has_text=f"{run_label} правка").click()
        row, modal = open_task_edit(page, title)
        expect(modal.locator(".task-edit-description textarea")).to_have_value(TASK_DESCRIPTION)

        modal.locator(".task-edit-title input").fill(new_title)
        modal.locator(".task-edit-deadline input").fill(DEADLINE_TEXT)
        modal.locator(".task-edit-deadline input").press("Enter")
        choose(page, ".task-edit-status", "Заблокирована")
        with page.expect_response(is_patch(path)) as saved:
            modal.get_by_role("button", name="Сохранить").click()
        assert saved.value.status == 200, f"правка задачи: {saved.value.status}"
        # описание не менялось — на сервер не ушло; срок — ISO с поясом
        assert set(sent(saved.value)) == {"title", "deadline", "status"}, sent(saved.value)
        assert sent(saved.value)["deadline"].endswith("Z"), sent(saved.value)
        expect(modal).to_have_count(0)

        row = page.locator(".n-drawer .task-item").filter(has_text=new_title)
        expect(row).to_have_count(1)
        expect(row).to_contain_text("Заблокирована")
        expect(row.locator(".task-deadline")).to_contain_text("2030")
        task = page.request.get(path, headers=headers).json()
        assert task["title"] == new_title
        assert task["status"] == "blocked"
        assert task["description"] == TASK_DESCRIPTION
        expected = page.evaluate("t => new Date(t).toISOString()", DEADLINE_TEXT.replace(" ", "T"))
        assert task["deadline"].replace("+00:00", "Z").startswith(expected[:16]), task["deadline"]
        expect(page.locator(".running-timer")).to_contain_text(new_title)
    finally:
        page.request.post("/api/time/timer/stop", headers=headers)
    assert s.net.foreign(base_url) == [], "запросы не на origin фронта"


def test_task_edit_clear_and_no_change(open_session, base_url, run_label):
    s = open_session()
    title = f"{run_label} очистка"
    headers, _, task_id = prepare(s, [f"{run_label} очистка проект"], title)
    page = s.page
    path = f"/api/tasks/tasks/{task_id}"
    page.locator(".project-card").filter(has_text=f"{run_label} очистка проект").click()

    # без изменений окно закрывается без запроса
    _, modal = open_task_edit(page, title)
    modal.get_by_role("button", name="Сохранить").click()
    expect(modal).to_have_count(0)
    assert s.net.api("PATCH", path) == [], "PATCH без изменений"

    # пустое название — тост, окно остаётся, запроса нет
    row, modal = open_task_edit(page, title)
    modal.locator(".task-edit-title input").fill("   ")
    modal.get_by_role("button", name="Сохранить").click()
    expect(page.locator(".n-message")).to_contain_text("Введите название задачи")
    expect(modal).to_have_count(1)
    assert s.net.api("PATCH", path) == [], "PATCH с пустым названием"

    # очищенное описание — null
    modal.locator(".task-edit-title input").fill(title)
    modal.locator(".task-edit-description textarea").fill("")
    with page.expect_response(is_patch(path)) as saved:
        modal.get_by_role("button", name="Сохранить").click()
    assert saved.value.status == 200, f"очистка описания: {saved.value.status}"
    assert sent(saved.value) == {"description": None}, sent(saved.value)
    expect(modal).to_have_count(0)
    expect(row.locator(".task-desc")).to_have_count(0)
    task = page.request.get(path, headers=headers).json()
    assert task["description"] is None
    assert task["title"] == title
    assert s.net.foreign(base_url) == [], "запросы не на origin фронта"


def test_task_edit_move_to_project(open_session, base_url, run_label):
    s = open_session()
    title = f"{run_label} перенос"
    first, second = f"{run_label} перенос из", f"{run_label} перенос в"
    headers, (_, second_id), task_id = prepare(s, [first, second], title)
    page = s.page
    path = f"/api/tasks/tasks/{task_id}"
    first_card = page.locator(".project-card").filter(has_text=first)
    second_card = page.locator(".project-card").filter(has_text=second)
    expect(first_card.locator(".task-item")).to_have_count(1)
    expect(second_card.locator(".task-item")).to_have_count(0)
    first_card.click()

    row, modal = open_task_edit(page, title)
    choose(page, ".task-edit-project", second)
    with page.expect_response(is_patch(path)) as saved:
        modal.get_by_role("button", name="Сохранить").click()
    assert saved.value.status == 200, f"перенос: {saved.value.status}"
    assert sent(saved.value) == {"project_id": second_id}, sent(saved.value)
    # из панели первого проекта пропала, на карточках счётчики перечитаны
    expect(row).to_have_count(0)
    expect(first_card.locator(".task-item")).to_have_count(0)
    expect(second_card.locator(".task-item")).to_have_count(1)
    expect(second_card.locator(".task-count")).to_have_text("(1)")
    assert page.request.get(path, headers=headers).json()["project_id"] == second_id
    assert s.net.foreign(base_url) == [], "запросы не на origin фронта"


def test_admin_task_edit_offers_only_owner_projects(open_session, base_url, run_label):
    title = f"{run_label} задача user1 у admin"
    own, other, foreign = (
        f"{run_label} admin из",
        f"{run_label} admin в",
        f"{run_label} проект user2",
    )
    u1 = open_session()
    _, (_, other_id), task_id = prepare(u1, [own, other], title)
    u2 = open_session()
    login(u2.page, USER2)
    r = u2.page.request.post(
        "/api/tasks/projects",
        headers={"Authorization": f"Bearer {local_storage(u2.page, 'access_token')}"},
        data={"name": foreign},
    )
    assert r.status == 201, f"создание проекта user2: {r.status}"

    adm = open_session()
    login(adm.page, ADMIN)
    page = adm.page
    path = f"/api/tasks/tasks/{task_id}"
    page.locator(".project-card").filter(has_text=own).click()
    _, modal = open_task_edit(page, title)
    page.locator(".task-edit-project").click()
    options = page.locator(".n-base-select-option")
    # проект владельца задачи есть, проект другого пользователя — нет (иначе перенос дал бы 400)
    expect(options.filter(has_text=other)).to_have_count(1)
    expect(options.filter(has_text=foreign)).to_have_count(0)
    options.filter(has_text=other).click()
    with page.expect_response(is_patch(path)) as saved:
        modal.get_by_role("button", name="Сохранить").click()
    assert saved.value.status == 200, f"перенос admin: {saved.value.status}"
    assert sent(saved.value) == {"project_id": other_id}, sent(saved.value)
    for s in (u1, u2, adm):
        assert s.net.foreign(base_url) == [], "запросы не на origin фронта"


def test_project_edit(open_session, base_url, run_label):
    s = open_session()
    name = f"{run_label} проект правка"
    new_name = f"{run_label} проект правка (новый)"
    headers, (project_id,), _ = prepare(s, [name], "")
    page = s.page
    path = f"/api/tasks/projects/{project_id}"
    card = page.locator(".project-card").filter(has_text=name)

    card.get_by_role("button", name="Изменить").click()
    modal = page.locator(".project-edit-modal")
    expect(modal.locator(".project-edit-name input")).to_have_value(name)
    modal.locator(".project-edit-name input").fill(new_name)
    with page.expect_response(is_patch(path)) as renamed:
        modal.get_by_role("button", name="Сохранить").click()
    assert renamed.value.status == 200, f"переименование: {renamed.value.status}"
    assert sent(renamed.value) == {"name": new_name}, sent(renamed.value)
    expect(modal).to_have_count(0)
    card = page.locator(".project-card").filter(has_text=new_name)
    expect(card).to_have_count(1)

    # переименование архивного проекта оставляет его в архиве
    with page.expect_response(is_patch(path)):
        card.get_by_role("button", name="В архив").click()
    expect(card).to_have_count(0)
    page.locator(".project-filters").get_by_role("switch").click()
    expect(card).to_have_count(1)
    final_name = f"{run_label} проект правка (архив)"
    card.get_by_role("button", name="Изменить").click()
    modal.locator(".project-edit-name input").fill(final_name)
    with page.expect_response(is_patch(path)) as archived:
        modal.get_by_role("button", name="Сохранить").click()
    assert archived.value.status == 200, f"переименование архивного: {archived.value.status}"
    assert sent(archived.value) == {"name": final_name}, sent(archived.value)
    expect(page.locator(".project-card").filter(has_text=final_name)).to_have_count(1)
    project = page.request.get(path, headers=headers).json()
    assert project["name"] == final_name
    assert project["is_active"] is False
    assert re.search(r"/dashboard$", page.url)
    assert s.net.foreign(base_url) == [], "запросы не на origin фронта"
