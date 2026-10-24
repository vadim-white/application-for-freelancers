"""Статистика admin: email из auth и роль после смены (stores/auth.ts, Dashboard.vue).

Статистика приходит из task и time с одними user_id, email и имена страница берёт у auth. Роль в
токене живёт до 15 минут, поэтому после смены роли при открытой сессии фронт сверяет /me с токеном
и один раз обновляет его. Seed-пользователей тест не меняет: повышается пользователь теста и
в конце снова user и отключён.
"""

import re
from datetime import UTC, datetime, timedelta

from playwright.sync_api import expect

from helpers import ADMIN, PASSWORD, USER1, api_path, local_storage, login

STATISTICS = "/api/tasks/statistics/users"


def api_login(s, email: str) -> dict:
    r = s.page.request.post("/api/auth/login", data={"email": email, "password": PASSWORD})
    assert r.status == 200, f"вход {email}: {r.status}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_statistics_shows_user_email(open_session, base_url, run_label):
    s = open_session()
    headers = api_login(s, USER1)
    # запись времени user1 создаёт тест: на записи smoke и других тестов он не опирается
    project = s.page.request.post(
        "/api/tasks/projects", headers=headers, data={"name": f"{run_label} статистика"}
    )
    assert project.status == 201, f"создание проекта: {project.status}"
    task = s.page.request.post(
        "/api/tasks/tasks",
        headers=headers,
        data={"title": f"{run_label} задача", "project_id": project.json()["id"]},
    )
    assert task.status == 201, f"создание задачи: {task.status}"
    stopped_at = datetime.now(UTC)
    entry = s.page.request.post(
        "/api/time/time-entries",
        headers=headers,
        data={
            "task_id": task.json()["id"],
            "started_at": (stopped_at - timedelta(minutes=5)).isoformat(),
            "stopped_at": stopped_at.isoformat(),
        },
    )
    assert entry.status == 201, f"запись времени: {entry.status}"

    login(s.page, ADMIN)
    with s.page.expect_response(lambda r: api_path(r.url) == STATISTICS) as stats:
        s.page.reload()
    assert stats.value.status == 200, f"статистика: {stats.value.status}"
    s.page.get_by_role("button", name="Статистика").click()
    expect(s.page.locator(".stats-table tbody tr").filter(has_text=USER1)).to_have_count(1)

    users = [r for r in s.net.responses if r[1] == "/api/auth/users"]
    assert users and all(st == 200 for _, _, st in users), f"список пользователей: {users}"
    assert s.net.foreign(base_url) == [], "запросы не на origin фронта"


def test_promoted_user_sees_statistics_after_reload(open_session, base_url, run_label):
    email = f"{run_label}-promo@example.com"
    s = open_session()
    registered = s.page.request.post(
        "/api/auth/register", data={"email": email, "password": PASSWORD}
    )
    assert registered.status == 201, f"регистрация {email}: {registered.status}"
    user_id = registered.json()["id"]
    admin_headers = api_login(s, ADMIN)

    def patch(body: dict) -> None:
        r = s.page.request.patch(f"/api/auth/users/{user_id}", headers=admin_headers, data=body)
        assert r.status == 200, f"PATCH {body}: {r.status}"

    try:
        # сессия открыта, пока он обычный user: токен несёт role=user
        login(s.page, email)
        expect(s.page.get_by_role("button", name="Статистика")).to_have_count(0)

        patch({"role": "admin"})
        s.net.clear()
        with s.page.expect_response(lambda r: api_path(r.url) == STATISTICS) as stats:
            s.page.reload()
        # без повторного входа: /me говорит admin, токен — user, фронт один раз обновляет токен
        assert stats.value.status == 200, f"статистика после смены роли: {stats.value.status}"
        expect(s.page.get_by_role("button", name="Статистика")).to_have_count(1)
        assert s.net.api("POST", "/api/auth/refresh") == [200], s.net.responses
        assert [r for r in s.net.responses if r[2] == 403] == [], s.net.responses
        assert local_storage(s.page, "access_token") is not None
        expect(s.page).to_have_url(re.compile(r"/dashboard$"))
        assert s.net.foreign(base_url) == [], "запросы не на origin фронта"
    finally:
        patch({"role": "user", "is_active": False})
