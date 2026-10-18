"""«Только свои»: проект user1 не виден user2 ни в API, ни на странице; admin видит всё."""

from playwright.sync_api import expect

from helpers import ADMIN, USER1, USER2, api_path, local_storage, login


def test_project_visible_to_owner_and_admin_only(open_session, base_url, run_label):
    name = f"{run_label} проект user1"

    # user1 создаёт проект через UI
    u1 = open_session()
    login(u1.page, USER1)
    u1.page.locator(".create-project-card").click()
    u1.page.get_by_placeholder("Введите название...").fill(name)
    with u1.page.expect_response(
        lambda r: r.request.method == "POST" and api_path(r.url) == "/api/tasks/projects"
    ) as created:
        u1.page.locator(".n-modal").get_by_role("button", name="Создать").click()
    assert created.value.status == 201, f"создание проекта: {created.value.status}"
    project = created.value.json()
    assert project["name"] == name
    expect(u1.page.locator(".project-card").filter(has_text=name)).to_have_count(1)

    # user2: нет в списке, по id — 404, на странице нет
    u2 = open_session()
    u2_projects = login(u2.page, USER2)
    assert project["id"] not in [p["id"] for p in u2_projects], (
        "user2 получил проект user1 в списке"
    )
    token = local_storage(u2.page, "access_token")
    direct = u2.page.request.get(
        f"/api/tasks/projects/{project['id']}", headers={"Authorization": f"Bearer {token}"}
    )
    assert direct.status == 404, f"user2: GET проекта user1 по id — {direct.status}, ожидался 404"
    # сначала дождаться, что отрисован весь полученный список, потом проверять отсутствие
    expect(u2.page.locator(".project-card")).to_have_count(len(u2_projects))
    expect(u2.page.locator(".project-card").filter(has_text=name)).to_have_count(0)

    # admin видит
    adm = open_session()
    admin_projects = login(adm.page, ADMIN)
    assert project["id"] in [p["id"] for p in admin_projects], "admin не получил проект user1"
    expect(adm.page.locator(".project-card").filter(has_text=name)).to_have_count(1)

    for s in (u1, u2, adm):
        assert s.net.foreign(base_url) == [], "запросы не на origin фронта"
