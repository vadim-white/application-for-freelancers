"""PATCH задач и проектов (merge-patch), PUT → 405; название и deadline на вводе."""

import pytest

TASKS = "/api/tasks/tasks"
PROJECTS = "/api/tasks/projects"
DEADLINE = "2026-03-01T12:00:00Z"


def _project(client, headers, name="p", **fields):
    r = client.post(PROJECTS, json={"name": name, **fields}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _task(client, headers, title="t", **fields):
    r = client.post(TASKS, json={"title": title, **fields}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _get(client, headers, path):
    r = client.get(path, headers=headers)
    assert r.status_code == 200
    return r.json()


def _full_task(client, headers):
    """Задача со всеми полями: в проекте p1, с описанием и сроком; p2 — для переноса."""
    p1 = _project(client, headers, "p1")
    p2 = _project(client, headers, "p2")
    tid = _task(client, headers, "t", description="d", deadline=DEADLINE, project_id=p1)
    return tid, p1, p2


def _ids_without_project(client, headers):
    return [x["id"] for x in _get(client, headers, f"{TASKS}?project_id=none")["items"]]


def _without(d, *keys):
    return {k: v for k, v in d.items() if k not in keys}


# --- Задача: каждое поле меняется само по себе ---

TASK_CHANGES = {
    "title": "new",
    "description": "new d",
    "status": "blocked",
    "deadline": "2026-04-02T08:30:00Z",
    "project_id": "p2",
    "is_active": False,
}


@pytest.mark.parametrize("field", TASK_CHANGES)
def test_patch_task_changes_only_given_field(client, user_headers, field):
    tid, _, p2 = _full_task(client, user_headers)
    value = p2 if TASK_CHANGES[field] == "p2" else TASK_CHANGES[field]
    before = _get(client, user_headers, f"{TASKS}/{tid}")
    assert before["updated_at"] is None
    r = client.patch(f"{TASKS}/{tid}", json={field: value}, headers=user_headers)
    assert r.status_code == 200, r.text
    after = _get(client, user_headers, f"{TASKS}/{tid}")
    assert after == r.json()
    if field == "deadline":
        # SQLite отдаёт срок без пояса, PostgreSQL — с Z: сравниваем момент без суффикса
        assert after["deadline"].removesuffix("Z") == value.removesuffix("Z")
    else:
        assert after[field] == value
    # остальное не тронуто; реальная правка ставит updated_at
    skip = (field, "updated_at", "project")
    assert _without(after, *skip) == _without(before, *skip)
    assert after["updated_at"] is not None


PROJECT_CHANGES = {"name": "new", "description": "new d", "is_active": False}


@pytest.mark.parametrize("field", PROJECT_CHANGES)
def test_patch_project_changes_only_given_field(client, user_headers, field):
    pid = _project(client, user_headers, "p", description="d")
    before = _get(client, user_headers, f"{PROJECTS}/{pid}")
    body = {field: PROJECT_CHANGES[field]}
    r = client.patch(f"{PROJECTS}/{pid}", json=body, headers=user_headers)
    assert r.status_code == 200, r.text
    after = _get(client, user_headers, f"{PROJECTS}/{pid}")
    assert after == r.json()
    assert after[field] == PROJECT_CHANGES[field]
    assert _without(after, field) == _without(before, field)


def test_patch_name_of_archived_project_keeps_archive(client, user_headers):
    # ProjectUpdate наследовал is_active=True: PUT {"name"} архивного проекта снимал архив
    pid = _project(client, user_headers)
    r = client.patch(f"{PROJECTS}/{pid}", json={"is_active": False}, headers=user_headers)
    assert r.json()["is_active"] is False
    r = client.patch(f"{PROJECTS}/{pid}", json={"name": "renamed"}, headers=user_headers)
    assert r.status_code == 200
    assert (r.json()["name"], r.json()["is_active"]) == ("renamed", False)
    assert _get(client, user_headers, f"{PROJECTS}/{pid}")["is_active"] is False


# --- null: очищает необязательные поля, у обязательных — 422 ---


def test_patch_task_null_clears_description_deadline_project(client, user_headers):
    tid, p1, _ = _full_task(client, user_headers)
    body = {"description": None, "deadline": None, "project_id": None}
    r = client.patch(f"{TASKS}/{tid}", json=body, headers=user_headers)
    assert r.status_code == 200, r.text
    t = _get(client, user_headers, f"{TASKS}/{tid}")
    assert (t["description"], t["deadline"], t["project_id"], t["project"]) == (None,) * 4
    assert (t["title"], t["owner_id"]) == ("t", 1)
    # вынесенная задача — среди задач без проекта, в проекте её нет
    assert _ids_without_project(client, user_headers) == [tid]
    assert _get(client, user_headers, f"{TASKS}?project_id={p1}")["items"] == []


def test_admin_moves_foreign_task_out_of_project_owner_kept(client, user_headers, admin_headers):
    tid, _, _ = _full_task(client, user_headers)
    r = client.patch(f"{TASKS}/{tid}", json={"project_id": None}, headers=admin_headers)
    assert r.status_code == 200
    assert (r.json()["project_id"], r.json()["owner_id"]) == (None, 1)
    # задача осталась у владельца, а не перешла к admin
    assert _ids_without_project(client, user_headers) == [tid]


def test_patch_project_null_clears_description(client, user_headers):
    pid = _project(client, user_headers, "p", description="d")
    r = client.patch(f"{PROJECTS}/{pid}", json={"description": None}, headers=user_headers)
    assert r.status_code == 200
    assert (r.json()["description"], r.json()["name"]) == (None, "p")


@pytest.mark.parametrize("field", ["title", "status", "is_active"])
def test_patch_task_null_required_field_422(client, user_headers, field):
    tid, _, _ = _full_task(client, user_headers)
    before = _get(client, user_headers, f"{TASKS}/{tid}")
    r = client.patch(f"{TASKS}/{tid}", json={field: None}, headers=user_headers)
    assert r.status_code == 422
    assert _get(client, user_headers, f"{TASKS}/{tid}") == before


@pytest.mark.parametrize("field", ["name", "is_active"])
def test_patch_project_null_required_field_422(client, user_headers, field):
    pid = _project(client, user_headers)
    before = _get(client, user_headers, f"{PROJECTS}/{pid}")
    r = client.patch(f"{PROJECTS}/{pid}", json={field: None}, headers=user_headers)
    assert r.status_code == 422
    assert _get(client, user_headers, f"{PROJECTS}/{pid}") == before


@pytest.mark.parametrize("body", [{"titel": "typo"}, {"owner_id": 2}, {"title": "x", "id": 5}])
def test_patch_task_unknown_field_422(client, user_headers, body):
    tid, _, _ = _full_task(client, user_headers)
    before = _get(client, user_headers, f"{TASKS}/{tid}")
    r = client.patch(f"{TASKS}/{tid}", json=body, headers=user_headers)
    assert r.status_code == 422
    assert _get(client, user_headers, f"{TASKS}/{tid}") == before


@pytest.mark.parametrize("body", [{"nmae": "typo"}, {"owner_id": 2}, {"name": "x", "id": 5}])
def test_patch_project_unknown_field_422(client, user_headers, body):
    pid = _project(client, user_headers)
    before = _get(client, user_headers, f"{PROJECTS}/{pid}")
    r = client.patch(f"{PROJECTS}/{pid}", json=body, headers=user_headers)
    assert r.status_code == 422
    assert _get(client, user_headers, f"{PROJECTS}/{pid}") == before


# --- Пустое тело и то же значение: без UPDATE ---


@pytest.mark.parametrize("body", [{}, {"title": "t"}, {"title": "  t  "}, {"status": "todo"}])
def test_patch_task_without_changes_keeps_updated_at(client, user_headers, body):
    tid, _, _ = _full_task(client, user_headers)
    before = _get(client, user_headers, f"{TASKS}/{tid}")
    r = client.patch(f"{TASKS}/{tid}", json=body, headers=user_headers)
    assert r.status_code == 200
    assert r.json() == before
    assert r.json()["updated_at"] is None


def test_patch_project_empty_body_no_changes(client, user_headers):
    pid = _project(client, user_headers, "p", description="d")
    before = _get(client, user_headers, f"{PROJECTS}/{pid}")
    r = client.patch(f"{PROJECTS}/{pid}", json={}, headers=user_headers)
    assert r.status_code == 200
    assert r.json() == before


# --- PUT больше нет ---


@pytest.mark.parametrize("kind", ["task", "project"])
def test_put_405(client, user_headers, kind):
    if kind == "task":
        path, body = f"{TASKS}/{_task(client, user_headers)}", {"title": "x"}
    else:
        path, body = f"{PROJECTS}/{_project(client, user_headers)}", {"name": "x"}
    before = _get(client, user_headers, path)
    r = client.put(path, json=body, headers=user_headers)
    assert r.status_code == 405
    assert _get(client, user_headers, path) == before


# --- Название: 1–255 после обрезки пробелов, в POST и PATCH ---

BAD_TITLES = ["", "   ", "x" * 256, " " + "x" * 256]


@pytest.mark.parametrize("title", BAD_TITLES)
def test_create_bad_title_422(client, user_headers, title):
    assert client.post(TASKS, json={"title": title}, headers=user_headers).status_code == 422
    assert client.post(PROJECTS, json={"name": title}, headers=user_headers).status_code == 422
    assert _get(client, user_headers, TASKS)["total"] == 0
    assert _get(client, user_headers, PROJECTS)["total"] == 0


@pytest.mark.parametrize("title", BAD_TITLES)
def test_patch_bad_title_422(client, user_headers, title):
    tid = _task(client, user_headers)
    pid = _project(client, user_headers)
    r = client.patch(f"{TASKS}/{tid}", json={"title": title}, headers=user_headers)
    assert r.status_code == 422
    r = client.patch(f"{PROJECTS}/{pid}", json={"name": title}, headers=user_headers)
    assert r.status_code == 422
    assert _get(client, user_headers, f"{TASKS}/{tid}")["title"] == "t"
    assert _get(client, user_headers, f"{PROJECTS}/{pid}")["name"] == "p"


def test_title_255_passes_and_spaces_trimmed(client, user_headers):
    long = "я" * 255
    r = client.post(TASKS, json={"title": f"  {long}  "}, headers=user_headers)
    assert (r.status_code, r.json()["title"]) == (201, long)
    r = client.post(PROJECTS, json={"name": f" {long} "}, headers=user_headers)
    assert (r.status_code, r.json()["name"]) == (201, long)
    tid = _task(client, user_headers)
    pid = _project(client, user_headers)
    r = client.patch(f"{TASKS}/{tid}", json={"title": "  new  "}, headers=user_headers)
    assert r.json()["title"] == "new"
    r = client.patch(f"{PROJECTS}/{pid}", json={"name": "\tnew\n"}, headers=user_headers)
    assert r.json()["name"] == "new"


# --- deadline только с часовым поясом ---


@pytest.mark.parametrize("deadline", ["2026-03-01T12:00:00", "2026-03-01"])
def test_deadline_without_timezone_422(client, user_headers, deadline):
    r = client.post(TASKS, json={"title": "t", "deadline": deadline}, headers=user_headers)
    assert r.status_code == 422
    tid = _task(client, user_headers, deadline=DEADLINE)
    r = client.patch(f"{TASKS}/{tid}", json={"deadline": deadline}, headers=user_headers)
    assert r.status_code == 422
    assert _get(client, user_headers, f"{TASKS}/{tid}")["deadline"].startswith("2026-03-01T12:00")


# --- PostgreSQL: длина названия и null ---


def test_title_256_on_postgres_422_not_500(pg_app, client, user_headers):
    # VARCHAR(255): без ограничения в схеме PostgreSQL отвечает 500, SQLite — 201
    long = "x" * 256
    assert client.post(TASKS, json={"title": long}, headers=user_headers).status_code == 422
    assert client.post(PROJECTS, json={"name": long}, headers=user_headers).status_code == 422
    tid = _task(client, user_headers)
    pid = _project(client, user_headers)
    r = client.patch(f"{TASKS}/{tid}", json={"title": long}, headers=user_headers)
    assert r.status_code == 422
    r = client.patch(f"{PROJECTS}/{pid}", json={"name": long}, headers=user_headers)
    assert r.status_code == 422
    r = client.patch(f"{TASKS}/{tid}", json={"title": "x" * 255}, headers=user_headers)
    assert r.status_code == 200


def test_patch_null_and_deadline_on_postgres(pg_app, client, user_headers):
    tid, _, _ = _full_task(client, user_headers)
    # смещение пересчитывается в UTC
    r = client.patch(
        f"{TASKS}/{tid}", json={"deadline": "2026-03-01T12:00:00+03:00"}, headers=user_headers
    )
    assert r.json()["deadline"] == "2026-03-01T09:00:00Z"
    body = {"deadline": None, "project_id": None, "description": None}
    r = client.patch(f"{TASKS}/{tid}", json=body, headers=user_headers)
    assert r.status_code == 200
    t = _get(client, user_headers, f"{TASKS}/{tid}")
    assert (t["deadline"], t["project_id"], t["description"]) == (None, None, None)
    assert t["owner_id"] == 1
    assert _ids_without_project(client, user_headers) == [tid]
