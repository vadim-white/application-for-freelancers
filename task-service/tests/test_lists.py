"""Списки задач и проектов: конверт, фильтры, сортировка, число SQL-запросов."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import event, update

from app import models
from app.db import engine

TASKS = "/api/tasks/tasks"
PROJECTS = "/api/tasks/projects"


def _project(client, headers, name="p"):
    r = client.post(PROJECTS, json={"name": name}, headers=headers)
    assert r.status_code == 201
    return r.json()["id"]


def _task(client, headers, title="t", **fields):
    r = client.post(TASKS, json={"title": title, **fields}, headers=headers)
    assert r.status_code == 201
    return r.json()["id"]


def _get(client, headers, path=TASKS, **params):
    r = client.get(path, params=params, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _ids(client, headers, path=TASKS, **params):
    return [x["id"] for x in _get(client, headers, path, **params)["items"]]


def _page(body):
    """(total, limit, offset, число элементов) конверта."""
    return body["total"], body["limit"], body["offset"], len(body["items"])


def _day(d):
    return datetime(2026, 1, d, tzinfo=UTC)


def _set_task(db_engine, task_id, **values):
    # updated_at передаётся всегда: иначе onupdate поставит now() при этой же правке
    values.setdefault("updated_at", None)
    with db_engine.begin() as conn:
        conn.execute(update(models.Task).where(models.Task.id == task_id).values(**values))


def _sort_dataset(client, headers, db_engine):
    """Пять задач с совпадениями в каждом поле, чтобы проверить и порядок, и id при равенстве.

    created_at — 3, 1, 2, 3, 4 (января); updated_at — нет, 5, нет, 2, нет;
    deadline — 1 марта, нет, 1 февраля, 1 февраля, нет; status — done, todo, blocked,
    in_progress, todo; title — b, a, A, B, c.
    """
    rows = [
        ("b", "done", _day(3), None, datetime(2026, 3, 1, tzinfo=UTC)),
        ("a", "todo", _day(1), _day(5), None),
        ("A", "blocked", _day(2), None, datetime(2026, 2, 1, tzinfo=UTC)),
        ("B", "in_progress", _day(3), _day(2), datetime(2026, 2, 1, tzinfo=UTC)),
        ("c", "todo", _day(4), None, None),
    ]
    ids = []
    for title, status, created, updated, deadline in rows:
        tid = _task(client, headers, title, status=status)
        _set_task(db_engine, tid, created_at=created, updated_at=updated, deadline=deadline)
        ids.append(tid)
    return ids


# индексы задач из _sort_dataset в ожидаемом порядке
TASK_SORTS = {
    "created_at": [1, 2, 0, 3, 4],
    "-created_at": [4, 3, 0, 2, 1],
    # coalesce(updated_at, created_at): 3, 5, 2, 2, 4 — задача без правок по created_at
    "updated_at": [2, 3, 0, 4, 1],
    "-updated_at": [1, 4, 0, 3, 2],
    # NULL в конце в обе стороны
    "deadline": [2, 3, 0, 1, 4],
    "-deadline": [0, 3, 2, 4, 1],
    # a, A, b, B, c: по lower, при равенстве id; по кодам символов было бы A, B, a, b, c
    "title": [1, 2, 0, 3, 4],
    "-title": [4, 3, 0, 2, 1],
    # todo, in_progress, done, blocked; по алфавиту было бы blocked, done, in_progress, todo
    "status": [1, 4, 3, 0, 2],
    "-status": [2, 0, 3, 4, 1],
}


@pytest.mark.parametrize("sort", TASK_SORTS)
def test_tasks_sort(client, user_headers, sort):
    ids = _sort_dataset(client, user_headers, engine)
    assert _ids(client, user_headers, sort=sort) == [ids[i] for i in TASK_SORTS[sort]]


def test_tasks_default_sort_newest_first(client, user_headers):
    ids = _sort_dataset(client, user_headers, engine)
    assert _ids(client, user_headers) == [ids[i] for i in TASK_SORTS["-created_at"]]


# порядок status, NULL и lower на PostgreSQL расходится с SQLite без CASE, nulls_last и lower
@pytest.mark.parametrize("sort", ["status", "-status", "deadline", "-deadline", "title", "-title"])
def test_tasks_sort_postgres(pg_app, client, user_headers, sort):
    ids = _sort_dataset(client, user_headers, pg_app.engine)
    assert _ids(client, user_headers, sort=sort) == [ids[i] for i in TASK_SORTS[sort]]


@pytest.mark.parametrize(
    ("sort", "expected"), [("title", ["А", "б", "Я", "я"]), ("-title", ["я", "Я", "б", "А"])]
)
def test_tasks_sort_title_cyrillic_postgres(pg_app, client, user_headers, sort, expected):
    # lower у SQLite приводит только ASCII: кириллица в другом регистре — только на PostgreSQL
    for title in ["Я", "б", "А", "я"]:
        _task(client, user_headers, title)
    items = _get(client, user_headers, sort=sort)["items"]
    assert [t["title"] for t in items] == expected


def test_tasks_envelope_and_total(client, user_headers):
    for i in range(3):
        _task(client, user_headers, f"t{i}", status="done" if i else "todo")
    body = _get(client, user_headers)
    assert sorted(body) == ["items", "limit", "offset", "total"]
    assert _page(body) == (3, 50, 0, 3)
    assert _page(_get(client, user_headers, limit=2, offset=2)) == (3, 2, 2, 1)
    # total — с тем же фильтром, а не размер страницы
    body = _get(client, user_headers, status="done", limit=1)
    assert (body["total"], len(body["items"])) == (2, 1)


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 201},
        {"offset": -1},
        {"sort": "bogus"},
        {"sort": "owner_id"},
        {"status": "bogus"},
        {"project_id": "x"},
        {"is_active": "maybe"},
    ],
)
def test_tasks_invalid_params_422(client, user_headers, params):
    assert client.get(TASKS, params=params, headers=user_headers).status_code == 422


def test_tasks_filters(client, user_headers):
    p1 = _project(client, user_headers)
    p2 = _project(client, user_headers)
    todo = _task(client, user_headers, project_id=p1)
    done = _task(client, user_headers, project_id=p1, status="done")
    blocked = _task(client, user_headers, project_id=p2, status="blocked")
    free = _task(client, user_headers, status="done")
    archived = _task(client, user_headers, project_id=p1, is_active=False)

    def ids(**params):
        return set(_ids(client, user_headers, **params))

    assert ids(project_id=p1) == {todo, done, archived}
    assert ids(project_id="none") == {free}
    assert ids(status="done") == {done, free}
    assert ids(status=["todo", "blocked"]) == {todo, blocked, archived}
    assert ids(is_active=False) == {archived}
    assert ids(is_active=True) == {todo, done, blocked, free}
    # вместе — пересечение
    assert ids(project_id=p1, status=["todo", "done"], is_active=True) == {todo, done}
    assert ids(project_id="none", status="todo") == set()
    assert _get(client, user_headers, project_id=p1, is_active=True)["total"] == 2


def test_tasks_only_own_inside_envelope(client, user_headers, other_headers, admin_headers):
    mine = _task(client, user_headers)
    theirs = _task(client, other_headers)
    body = _get(client, user_headers)
    assert ([t["id"] for t in body["items"]], body["total"]) == ([mine], 1)
    # фильтр без проекта не выводит за пределы своих
    assert _ids(client, user_headers, project_id="none") == [mine]
    body = _get(client, admin_headers)
    assert (set(t["id"] for t in body["items"]), body["total"]) == ({mine, theirs}, 2)


def test_tasks_query_count_does_not_grow_with_projects(client, user_headers):
    statements = []

    def count(*_args):
        statements.append(1)

    def queries_for_list():
        statements.clear()
        event.listen(engine, "before_cursor_execute", count)
        try:
            body = _get(client, user_headers, limit=200)
        finally:
            event.remove(engine, "before_cursor_execute", count)
        # вложенный project есть у каждой задачи — его догрузка тоже посчитана
        assert all(t["project"] is not None for t in body["items"])
        return len(statements)

    for i in range(2):
        _task(client, user_headers, project_id=_project(client, user_headers, f"p{i}"))
    few = queries_for_list()
    for i in range(2, 8):
        _task(client, user_headers, project_id=_project(client, user_headers, f"p{i}"))
    many = queries_for_list()
    # count, страница задач, их проекты одним запросом
    assert few == many == 3


# --- Проекты ---


def test_projects_envelope_total_and_filter(client, user_headers):
    active = [_project(client, user_headers, f"p{i}") for i in range(3)]
    archived = _project(client, user_headers, "archived")
    r = client.patch(f"{PROJECTS}/{archived}", json={"is_active": False}, headers=user_headers)
    assert r.status_code == 200
    body = _get(client, user_headers, PROJECTS, limit=2)
    assert sorted(body) == ["items", "limit", "offset", "total"]
    assert _page(body) == (4, 2, 0, 2)
    assert _get(client, user_headers, PROJECTS)["limit"] == 50
    assert _ids(client, user_headers, PROJECTS, is_active=False) == [archived]
    body = _get(client, user_headers, PROJECTS, is_active=True)
    assert ({p["id"] for p in body["items"]}, body["total"]) == (set(active), 3)


# индексы проектов: name — b, a, A, c; created_at — 2, 1, 2, 3 (января)
PROJECT_SORTS = {
    "created_at": [1, 0, 2, 3],
    "-created_at": [3, 2, 0, 1],
    "name": [1, 2, 0, 3],
    "-name": [3, 0, 2, 1],
}


@pytest.mark.parametrize("sort", PROJECT_SORTS)
def test_projects_sort(client, user_headers, sort):
    ids = []
    for name, created in [
        ("b", _day(2)),
        ("a", _day(1)),
        ("A", _day(2)),
        ("c", _day(3)),
    ]:
        pid = _project(client, user_headers, name)
        # у проекта нет updated_at — onupdate не мешает
        with engine.begin() as conn:
            conn.execute(
                update(models.Project).where(models.Project.id == pid).values(created_at=created)
            )
        ids.append(pid)
    expected = [ids[i] for i in PROJECT_SORTS[sort]]
    assert _ids(client, user_headers, PROJECTS, sort=sort) == expected
    if sort == "-created_at":
        assert _ids(client, user_headers, PROJECTS) == expected  # по умолчанию


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 201},
        {"offset": -1},
        {"sort": "bogus"},
        {"sort": "title"},
    ],
)
def test_projects_invalid_params_422(client, user_headers, params):
    assert client.get(PROJECTS, params=params, headers=user_headers).status_code == 422


def test_projects_only_own_inside_envelope(client, user_headers, other_headers, admin_headers):
    mine = _project(client, user_headers)
    theirs = _project(client, other_headers)
    body = _get(client, user_headers, PROJECTS)
    assert ([p["id"] for p in body["items"]], body["total"]) == ([mine], 1)
    body = _get(client, admin_headers, PROJECTS)
    assert (set(p["id"] for p in body["items"]), body["total"]) == ({mine, theirs}, 2)


# --- Счётчик и превью задач в списке проектов ---


def _preview_dataset(client, headers):
    """Проекты: p0 — пять активных задач и одна архивная, p1 — одна, p2 — без задач."""
    pids = [_project(client, headers, f"p{i}") for i in range(3)]
    # названия против порядка создания: превью идёт по created_at, а не по title
    tasks = [_task(client, headers, f"a{4 - i}", project_id=pids[0]) for i in range(5)]
    statuses = ["todo", "in_progress", "done", "blocked", "todo"]
    for tid, st in zip(tasks, statuses, strict=True):
        r = client.patch(f"{TASKS}/{tid}", json={"status": st}, headers=headers)
        assert r.status_code == 200
    archived = _task(client, headers, "archived", project_id=pids[0])
    r = client.patch(f"{TASKS}/{archived}", json={"is_active": False}, headers=headers)
    assert r.status_code == 200
    single = _task(client, headers, "single", project_id=pids[1])
    # задачи без проекта в счётчик не попадают
    _task(client, headers, "free")
    return pids, tasks, single


def _by_id(body):
    return {p["id"]: p for p in body["items"]}


def test_projects_tasks_count_and_preview(client, user_headers):
    (p0, p1, p2), tasks, single = _preview_dataset(client, user_headers)
    projects = _by_id(_get(client, user_headers, PROJECTS))
    # архивная задача не считается, превью — три первые активные по created_at, id
    assert projects[p0]["tasks_count"] == 5
    assert projects[p0]["tasks_preview"] == [
        {"id": tasks[0], "title": "a4", "status": "todo"},
        {"id": tasks[1], "title": "a3", "status": "in_progress"},
        {"id": tasks[2], "title": "a2", "status": "done"},
    ]
    assert projects[p1]["tasks_count"] == 1
    assert projects[p1]["tasks_preview"] == [{"id": single, "title": "single", "status": "todo"}]
    assert projects[p2]["tasks_count"] == 0
    assert projects[p2]["tasks_preview"] == []


def test_projects_tasks_summary_ignores_page_and_filters(client, user_headers):
    (p0, p1, _), _, _ = _preview_dataset(client, user_headers)
    # на второй странице и под фильтром счётчики те же
    body = _get(client, user_headers, PROJECTS, sort="created_at", limit=1, offset=1)
    assert [(p["id"], p["tasks_count"]) for p in body["items"]] == [(p1, 1)]
    body = _get(client, user_headers, PROJECTS, is_active=True, limit=1, sort="created_at")
    assert [(p["id"], p["tasks_count"]) for p in body["items"]] == [(p0, 5)]


def test_projects_tasks_summary_of_foreign_projects_for_admin(
    client, user_headers, other_headers, admin_headers
):
    (p0, _, _), _, _ = _preview_dataset(client, other_headers)
    mine = _project(client, user_headers)
    _task(client, user_headers, project_id=mine)
    projects = _by_id(_get(client, admin_headers, PROJECTS))
    assert (projects[p0]["tasks_count"], len(projects[p0]["tasks_preview"])) == (5, 3)
    assert projects[mine]["tasks_count"] == 1
    # user не видит чужой проект и его задачи
    assert p0 not in _by_id(_get(client, user_headers, PROJECTS))


def test_projects_empty_page_skips_task_queries(client, user_headers):
    statements = []

    def record(_conn, _cursor, statement, *_args):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        body = _get(client, user_headers, PROJECTS)
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert body["items"] == []
    # только count конверта и пустая страница
    assert len(statements) == 2


def test_projects_query_count_does_not_grow_with_projects(client, user_headers):
    statements = []

    def count(*_args):
        statements.append(1)

    def queries_for_list():
        statements.clear()
        event.listen(engine, "before_cursor_execute", count)
        try:
            body = _get(client, user_headers, PROJECTS, limit=200)
        finally:
            event.remove(engine, "before_cursor_execute", count)
        assert all(p["tasks_count"] == 1 for p in body["items"])
        return len(statements)

    for i in range(2):
        _task(client, user_headers, project_id=_project(client, user_headers, f"p{i}"))
    few = queries_for_list()
    for i in range(2, 8):
        _task(client, user_headers, project_id=_project(client, user_headers, f"p{i}"))
    many = queries_for_list()
    # count, страница проектов, счётчики, превью
    assert few == many == 4


def test_summary_fields_only_in_list(client, user_headers):
    pid = _project(client, user_headers)
    tid = _task(client, user_headers, project_id=pid)
    one = _get(client, user_headers, f"{PROJECTS}/{pid}")
    assert "tasks_count" not in one and "tasks_preview" not in one
    nested = _get(client, user_headers, f"{TASKS}/{tid}")["project"]
    assert "tasks_count" not in nested and "tasks_preview" not in nested
    listed = _get(client, user_headers)["items"][0]["project"]
    assert "tasks_count" not in listed and "tasks_preview" not in listed


def test_projects_tasks_summary_postgres(pg_app, client, user_headers):
    # оконная функция и GROUP BY на PostgreSQL: тот же счётчик и превью, что на SQLite
    (p0, p1, p2), tasks, single = _preview_dataset(client, user_headers)
    projects = _by_id(_get(client, user_headers, PROJECTS))
    assert projects[p0]["tasks_count"] == 5
    assert [t["id"] for t in projects[p0]["tasks_preview"]] == tasks[:3]
    assert projects[p0]["tasks_preview"][1]["status"] == "in_progress"
    assert [t["id"] for t in projects[p1]["tasks_preview"]] == [single]
    assert (projects[p2]["tasks_count"], projects[p2]["tasks_preview"]) == (0, [])
