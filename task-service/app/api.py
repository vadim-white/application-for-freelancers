import logging
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from . import crud, models, schemas
from .core.auth import CurrentUser, get_current_user, require_admin
from .deps import get_db
from .time_client import get_time_client

logger = logging.getLogger(__name__)

# Все эндпоинты требуют валидный access-токен (401 без него)
router = APIRouter(dependencies=[Depends(get_current_user)])

# --- Доступ: user работает только со своим, admin — со всем ---
# Чужой объект для user неотличим от несуществующего: 404, а не 403,
# чтобы не раскрывать, что такой id есть


def _owner_scope(user: CurrentUser) -> int | None:
    """owner_id для фильтра списков: у admin без фильтра."""
    return None if user.is_admin else user.id


def get_owned_project(db: Session, project_id: int, user: CurrentUser) -> models.Project:
    p = crud.get_project(db, project_id)
    if p is None or (not user.is_admin and p.owner_id != user.id):
        raise HTTPException(status_code=404, detail="Project not found")
    return p


def get_owned_task(db: Session, task_id: int, user: CurrentUser) -> models.Task:
    t = crud.get_task(db, task_id)
    if t is None or (not user.is_admin and t.owner_id != user.id):
        raise HTTPException(status_code=404, detail="Task not found")
    return t


# --- Projects ---
@router.post("/projects", response_model=schemas.ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    project_in: schemas.ProjectCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    project = crud.create_project(db, project_in, owner_id=user.id)
    logger.info(f"Project created: id={project.id}, owner_id={project.owner_id}")
    return project


@router.get("/projects", response_model=schemas.ProjectList)
def list_projects(
    is_active: bool | None = None,
    sort: Literal["created_at", "-created_at", "name", "-name"] = "-created_at",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    items, total = crud.list_projects(
        db,
        owner_id=_owner_scope(user),
        is_active=is_active,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/projects/{project_id}", response_model=schemas.ProjectRead)
def get_project(
    project_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
):
    return get_owned_project(db, project_id, user)


@router.put("/projects/{project_id}", response_model=schemas.ProjectRead)
def update_project(
    project_id: int,
    update_in: schemas.ProjectUpdate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    p = get_owned_project(db, project_id, user)
    return crud.update_project(db, p, update_in)


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
):
    p = get_owned_project(db, project_id, user)
    crud.delete_project(db, p)
    logger.info(f"Project deleted: id={project_id}")
    return None


# --- Tasks ---
@router.post("/tasks", response_model=schemas.TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(
    task_in: schemas.TaskCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    # Задача в проекте принадлежит владельцу проекта: admin в чужом проекте владельцем не станет.
    # is not None: project_id=0 тоже проверяется, иначе на PostgreSQL 500 от внешнего ключа
    owner_id = user.id
    if task_in.project_id is not None:
        owner_id = get_owned_project(db, task_in.project_id, user).owner_id
    task = crud.create_task(db, task_in, owner_id=owner_id)
    logger.info(
        f"Task created: id={task.id}, project_id={task.project_id}, owner_id={task.owner_id}"
    )
    return task


TaskSort = Literal[
    "created_at",
    "-created_at",
    "updated_at",
    "-updated_at",
    "deadline",
    "-deadline",
    "title",
    "-title",
    "status",
    "-status",
]


@router.get("/tasks", response_model=schemas.TaskList)
def list_tasks(
    project_id: int | Literal["none"] | None = None,
    status_filter: list[models.TaskStatus] = Query([], alias="status"),
    is_active: bool | None = None,
    sort: TaskSort = "-created_at",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """project_id=none — задачи без проекта; status повторяется: ?status=todo&status=done."""
    items, total = crud.list_tasks(
        db,
        owner_id=_owner_scope(user),
        project_id=project_id,
        statuses=status_filter,
        is_active=is_active,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/tasks/{task_id}", response_model=schemas.TaskRead)
def get_task(
    task_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
):
    return get_owned_task(db, task_id, user)


@router.put("/tasks/{task_id}", response_model=schemas.TaskRead)
def update_task(
    task_id: int,
    update_in: schemas.TaskUpdate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    logger.info(f"Updating task: id={task_id}, update={update_in.model_dump()}")
    t = get_owned_task(db, task_id, user)
    # Перенос только в проект владельца задачи. user в чужой проект получает 404 из
    # get_owned_project; admin видит все проекты, поэтому для него отдельный 400
    if update_in.project_id is not None:
        target = get_owned_project(db, update_in.project_id, user)
        if target.owner_id != t.owner_id:
            raise HTTPException(status_code=400, detail="Project belongs to another owner")
    result = crud.update_task(db, t, update_in)
    logger.info(f"Task updated: id={task_id}, new_status={result.status}")
    return result


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
):
    t = get_owned_task(db, task_id, user)
    crud.delete_task(db, t)
    logger.info(f"Task deleted: id={task_id}")
    return None


@router.post("/tasks/{task_id}/status", response_model=schemas.TaskRead)
def change_status(
    task_id: int,
    status_in: schemas.TaskStatusUpdate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    logger.info(f"Changing task status: id={task_id}, new_status={status_in.status.value}")
    t = get_owned_task(db, task_id, user)
    t.status = status_in.status
    db.add(t)
    db.commit()
    db.refresh(t)
    logger.info(f"Task status changed: id={task_id}, new_status={t.status}")
    return t


# --- Statistics ---
@router.get("/statistics/users")
async def get_users_statistics(
    user: CurrentUser = Depends(require_admin),
    client: httpx.AsyncClient = Depends(get_time_client),
):
    """Статистика по пользователям: кол-во задач и среднее время (только admin)"""
    logger.info("Getting users statistics")

    # time-service сам проверяет токен, поэтому пробрасываем Authorization пользователя
    try:
        response = await client.get(
            "/api/time/statistics/users", headers={"Authorization": user.authorization}
        )
    except httpx.HTTPError as e:
        logger.error(f"Error getting statistics from time-service: {e}")
        raise HTTPException(status_code=502, detail="Time service unavailable") from e

    if response.status_code != 200:
        logger.error(f"Failed to get statistics from time-service: {response.status_code}")
        raise HTTPException(status_code=502, detail="Failed to get statistics")

    stats = response.json()
    logger.info(f"Statistics retrieved: {len(stats)} users")
    return stats
