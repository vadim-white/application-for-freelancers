"""Архив, страницы и сортировка (frontend/login_page/src: Dashboard.vue, ProjectTasksDrawer.vue).

Дашборд показывает проекты страницами по 20 и по умолчанию только активные; «Показать архив» —
только архивные. Панель проекта — «Текущие» и «Выполненные» двумя запросами со своими страницами,
тоже по 20, переключатель архива и выбор сортировки. У архивной задачи нет кнопок таймера и
«Выполнена». Объекты создаются через API: тест проверяет страницу, а не форму создания.
"""

from playwright.sync_api import Page, expect

from helpers import USER1, Session, api_path, is_projects_list, local_storage, login

PAGE_SIZE = 20


def prepare(s: Session, name: str, titles: list[str]) -> tuple[int, dict[str, int]]:
    """Вход user1, проект с задачами через API, перезагрузка дашборда; id проекта и задач."""
    login(s.page, USER1)
    headers = {"Authorization": f"Bearer {local_storage(s.page, 'access_token')}"}
    created = s.page.request.post("/api/tasks/projects", headers=headers, data={"name": name})
    assert created.status == 201, f"создание проекта: {created.status}"
    project_id = created.json()["id"]
    ids = {}
    for title in titles:
        r = s.page.request.post(
            "/api/tasks/tasks", headers=headers, data={"title": title, "project_id": project_id}
        )
        assert r.status == 201, f"создание задачи {title}: {r.status}"
        ids[title] = r.json()["id"]
    # дашборд грузит проекты при открытии — перезагрузка подхватывает созданное
    s.page.reload()
    return project_id, ids


def choose(page: Page, select: str, label: str) -> None:
    page.locator(select).click()
    page.locator(".n-base-select-option").filter(has_text=label).click()


def patch_ok(page: Page, path: str):
    """Ожидание PATCH по пути; проверка кода после действия."""
    return page.expect_response(lambda r: r.request.method == "PATCH" and api_path(r.url) == path)


def test_project_archive_and_restore(open_session, base_url, run_label):
    s = open_session()
    name = f"{run_label} архив проекта"
    project_id, _ = prepare(s, name, [])
    page = s.page
    card = page.locator(".project-card").filter(has_text=name)
    expect(card).to_have_count(1)

    with patch_ok(page, f"/api/tasks/projects/{project_id}") as archived:
        card.get_by_role("button", name="В архив").click()
    assert archived.value.status == 200, f"в архив: {archived.value.status}"
    expect(card).to_have_count(0)

    switch = page.locator(".project-filters").get_by_role("switch")
    switch.click()
    expect(card).to_have_count(1)
    with patch_ok(page, f"/api/tasks/projects/{project_id}") as restored:
        card.get_by_role("button", name="Восстановить").click()
    assert restored.value.status == 200, f"восстановить: {restored.value.status}"
    expect(card).to_have_count(0)

    switch.click()
    expect(card).to_have_count(1)
    expect(card.get_by_role("button", name="В архив")).to_have_count(1)

    # сортировка уходит в запрос
    with page.expect_response(lambda r: is_projects_list(r) and "sort=name" in r.url) as by_name:
        choose(page, ".project-sort", "Название А–Я")
    assert by_name.value.status == 200, f"сортировка по названию: {by_name.value.status}"
    assert s.net.foreign(base_url) == [], "запросы не на origin фронта"


def test_task_archive_and_restore(open_session, base_url, run_label):
    s = open_session()
    name = f"{run_label} архив задачи"
    title = f"{run_label} задача в архив"
    _, ids = prepare(s, name, [title])
    page = s.page
    card = page.locator(".project-card").filter(has_text=name)
    expect(card.locator(".task-item")).to_have_count(1)
    card.click()
    row = page.locator(".n-drawer .task-item").filter(has_text=title)
    expect(row).to_have_count(1)

    with patch_ok(page, f"/api/tasks/tasks/{ids[title]}") as archived:
        row.get_by_role("button", name="В архив").click()
    assert archived.value.status == 200, f"в архив: {archived.value.status}"
    expect(row).to_have_count(0)
    # карточка перечитала список проектов: счётчик и превью считают только активные задачи
    expect(card.locator(".task-item")).to_have_count(0)

    page.locator(".n-drawer .task-filters").get_by_role("switch").click()
    expect(row).to_have_count(1)
    expect(row.get_by_role("button", name="Открыть таймер")).to_have_count(0)
    expect(row.get_by_role("button", name="Отметить выполненной")).to_have_count(0)

    with patch_ok(page, f"/api/tasks/tasks/{ids[title]}") as restored:
        row.get_by_role("button", name="Восстановить").click()
    assert restored.value.status == 200, f"восстановить: {restored.value.status}"
    expect(row).to_have_count(0)
    expect(card.locator(".task-item")).to_have_count(1)

    page.locator(".n-drawer .task-filters").get_by_role("switch").click()
    expect(row).to_have_count(1)
    expect(row.get_by_role("button", name="Открыть таймер")).to_have_count(1)
    assert s.net.foreign(base_url) == [], "запросы не на origin фронта"


def test_task_pages_and_sort(open_session, base_url, run_label):
    s = open_session()
    name = f"{run_label} страницы задач"
    titles = [f"{run_label} task {i:02d}" for i in range(1, PAGE_SIZE + 2)]
    prepare(s, name, titles)
    page = s.page
    page.locator(".project-card").filter(has_text=name).click()
    rows = page.locator(".n-drawer .tasks-current .task-item")
    first = page.locator(".n-drawer .tasks-current .task-title").first

    # 21 задача: на первой странице 20, на второй одна; по умолчанию старые сверху
    expect(rows).to_have_count(PAGE_SIZE)
    expect(first).to_have_text(titles[0])
    page.locator(".n-drawer .tasks-current .n-pagination").get_by_text("2", exact=True).click()
    expect(rows).to_have_count(1)
    expect(first).to_have_text(titles[-1])

    # смена сортировки возвращает на первую страницу, порядок обратный
    choose(page, ".n-drawer .task-sort", "Название Я–А")
    expect(rows).to_have_count(PAGE_SIZE)
    expect(first).to_have_text(titles[-1])
    choose(page, ".n-drawer .task-sort", "Название А–Я")
    expect(first).to_have_text(titles[0])
    assert s.net.foreign(base_url) == [], "запросы не на origin фронта"
