"""Серверный таймер в окне задачи (frontend/login_page/src/stores/timer.ts, TaskTimerModal.vue).

Состояние таймера живёт в time-service: страница его только показывает и перечитывает. Окно таймера
одно на дашборд — задача подставляется при открытии, время одной задачи не должно попасть в другую.
У пользователя один идущий таймер, поэтому каждый тест останавливает его до и после себя.
"""

import re
from collections.abc import Callable
from datetime import datetime

from playwright.sync_api import Locator, Page, Response, expect

from helpers import USER1, Session, api_path, local_storage, login


def is_api(method: str, path: str) -> Callable[[Response], bool]:
    return lambda r: r.request.method == method and api_path(r.url) == path


START = is_api("POST", "/api/time/timer/start")
STOP = is_api("POST", "/api/time/timer/stop")


def prepare(s: Session, run_label: str, kind: str, titles: list[str]) -> tuple[dict, str, dict]:
    """Вход user1, остановка его таймера, проект с задачами; возвращает заголовки, имя, id задач."""
    login(s.page, USER1)
    headers = {"Authorization": f"Bearer {local_storage(s.page, 'access_token')}"}
    stop_timer(s, headers)
    name = f"{run_label} {kind}"
    created = s.page.request.post("/api/tasks/projects", headers=headers, data={"name": name})
    assert created.status == 201, f"создание проекта: {created.status}"
    ids = {}
    for title in titles:
        r = s.page.request.post(
            "/api/tasks/tasks",
            headers=headers,
            data={"title": f"{run_label} {title}", "project_id": created.json()["id"]},
        )
        assert r.status == 201, f"создание задачи {title}: {r.status}"
        ids[title] = r.json()["id"]
    # дашборд грузит проекты при открытии — перезагрузка подхватывает созданное
    s.page.reload()
    s.page.locator(".project-card").filter(has_text=name).click()
    return headers, name, ids


def stop_timer(s: Session, headers: dict) -> None:
    r = s.page.request.post("/api/time/timer/stop", headers=headers)
    assert r.status == 200, f"остановка таймера: {r.status}"


def open_task(page: Page, title: str) -> Locator:
    page.locator(".n-drawer .task-item").filter(has_text=title).get_by_role(
        "button", name="⏱️"
    ).click()
    modal = page.locator(".timer-modal")
    expect(modal).to_contain_text(title)
    return modal


def start(page: Page, modal: Locator) -> dict:
    with page.expect_response(START) as started:
        modal.get_by_role("button", name="Старт").click()
    assert started.value.status == 201, f"старт таймера: {started.value.status}"
    return started.value.json()


def pause(page: Page, modal: Locator) -> dict:
    with page.expect_response(STOP) as stopped:
        modal.get_by_role("button", name="Пауза").click()
    assert stopped.value.status == 200, f"стоп таймера: {stopped.value.status}"
    return stopped.value.json()


def test_running_timer_survives_reload(open_session, base_url, run_label):
    s = open_session()
    headers, _, ids = prepare(s, run_label, "перезагрузка", ["задача"])
    title = f"{run_label} задача"
    try:
        start(s.page, open_task(s.page, title))
        s.page.locator(".timer-modal").get_by_role("button", name="Закрыть").click()

        with s.page.expect_response(is_api("GET", "/api/time/timer")) as state:
            s.page.reload()
        assert state.value.status == 200, f"GET /api/time/timer: {state.value.status}"
        assert state.value.json()["entry"]["task_id"] == ids["задача"]

        indicator = s.page.locator(".running-timer")
        expect(indicator).to_contain_text(title)
        expect(indicator).not_to_contain_text("00:00:00")
        # индикатор открывает окно идущей задачи, из него таймер останавливается
        indicator.click()
        modal = s.page.locator(".timer-modal")
        expect(modal).to_contain_text(title)
        assert pause(s.page, modal)["stopped"]["task_id"] == ids["задача"]
        expect(indicator).to_have_count(0)
        assert s.net.foreign(base_url) == [], "запросы не на origin фронта"
    finally:
        stop_timer(s, headers)


def test_short_entry_is_saved(open_session, run_label):
    s = open_session()
    headers, _, ids = prepare(s, run_label, "короткая запись", ["задача"])
    try:
        modal = open_task(s.page, f"{run_label} задача")
        start(s.page, modal)
        # раньше запись короче 30 с уходила как minutes: 0 и получала 422
        expect(modal.locator(".timer-value")).to_have_text(re.compile(r"00:00:(0[6-9]|[1-5]\d)"))
        stopped = pause(s.page, modal)["stopped"]
        assert stopped["task_id"] == ids["задача"]
        assert stopped["duration_seconds"] >= 5, stopped
        assert stopped["stopped_at"] is not None
        assert [r for r in s.net.responses if r[2] == 422] == [], s.net.responses
    finally:
        stop_timer(s, headers)


def test_stop_does_not_mark_task_done(open_session, run_label):
    s = open_session()
    headers, _, ids = prepare(s, run_label, "стоп без done", ["задача"])
    task_path = f"/api/tasks/tasks/{ids['задача']}"
    try:
        modal = open_task(s.page, f"{run_label} задача")
        # старт переводит задачу из todo в in_progress отдельным запросом в task
        with s.page.expect_response(is_api("PUT", task_path)) as put:
            start(s.page, modal)
        assert put.value.status == 200 and put.value.json()["status"] == "in_progress"
        expect(modal.locator(".task-status")).to_have_text("in_progress")

        pause(s.page, modal)
        expect(s.page.get_by_text("Записано 00:00:")).to_be_visible()
        expect(modal.locator(".task-status")).to_have_text("in_progress")
        task = s.page.request.get(task_path, headers=headers)
        assert task.status == 200 and task.json()["status"] == "in_progress", task.json()
    finally:
        stop_timer(s, headers)


def test_time_of_task_a_is_not_written_to_b(open_session, run_label):
    s = open_session()
    headers, _, ids = prepare(s, run_label, "задачи А и Б", ["А", "Б"])
    a, b = f"{run_label} А", f"{run_label} Б"
    try:
        modal = open_task(s.page, a)
        start(s.page, modal)
        modal.get_by_role("button", name="Закрыть").click()

        # то же окно для Б: таймер Б не идёт, окно показывает, что идёт А
        modal = open_task(s.page, b)
        expect(modal.locator(".timer-value")).to_have_text("00:00:00")
        expect(modal.locator(".other-timer")).to_contain_text(a)
        expect(modal.get_by_role("button", name="Пауза")).to_be_disabled()

        switched = start(s.page, modal)
        assert switched["entry"]["task_id"] == ids["Б"]
        assert switched["stopped"]["task_id"] == ids["А"]
        expect(s.page.get_by_text(f"Таймер на «{a}» остановлен")).to_be_visible()
        assert pause(s.page, modal)["stopped"]["task_id"] == ids["Б"]

        entries = {}
        for key in ("А", "Б"):
            r = s.page.request.get(
                "/api/time/time-entries", headers=headers, params={"task_id": ids[key]}
            )
            assert r.status == 200, f"записи задачи {key}: {r.status}"
            entries[key] = r.json()
        assert len(entries["А"]) == 1 and len(entries["Б"]) == 1, entries
        # запись Б начинается не раньше, чем закрыта запись А: время А в Б не попало
        b_started = datetime.fromisoformat(entries["Б"][0]["started_at"])
        assert b_started >= datetime.fromisoformat(entries["А"][0]["stopped_at"]), entries
    finally:
        stop_timer(s, headers)
