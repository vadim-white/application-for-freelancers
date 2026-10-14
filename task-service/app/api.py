from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from . import schemas, crud, models
from .deps import get_db
from .core.auth import CurrentUser, get_current_user, require_admin
from .core.config import settings
from typing import List, Optional
import httpx
import logging

logger = logging.getLogger(__name__)

# Все эндпоинты требуют валидный access-токен (401 без него)
router = APIRouter(dependencies=[Depends(get_current_user)])

# --- Доступ: user работает только со своим, admin — со всем ---
# Чужой объект для user неотличим от несуществующего: 404, а не 403,
# чтобы не раскрывать, что такой id есть

def _owner_scope(user: CurrentUser) -> Optional[int]:
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
def create_project(project_in: schemas.ProjectCreate, db: Session = Depends(get_db),
                   user: CurrentUser = Depends(get_current_user)):
    project = crud.create_project(db, project_in, owner_id=user.id)
    logger.info(f"Project created: id={project.id}, owner_id={project.owner_id}")
    return project

@router.get("/projects", response_model=List[schemas.ProjectRead])
def list_projects(skip: int = 0, limit: int = 100, db: Session = Depends(get_db),
                  user: CurrentUser = Depends(get_current_user)):
    return crud.list_projects(db, skip=skip, limit=limit, owner_id=_owner_scope(user))

@router.get("/projects/{project_id}", response_model=schemas.ProjectRead)
def get_project(project_id: int, db: Session = Depends(get_db),
                user: CurrentUser = Depends(get_current_user)):
    return get_owned_project(db, project_id, user)

@router.put("/projects/{project_id}", response_model=schemas.ProjectRead)
def update_project(project_id: int, update_in: schemas.ProjectUpdate, db: Session = Depends(get_db),
                   user: CurrentUser = Depends(get_current_user)):
    p = get_owned_project(db, project_id, user)
    return crud.update_project(db, p, update_in)

@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: int, db: Session = Depends(get_db),
                   user: CurrentUser = Depends(get_current_user)):
    p = get_owned_project(db, project_id, user)
    crud.delete_project(db, p)
    logger.info(f"Project deleted: id={project_id}")
    return {}

# --- Tasks ---
@router.post("/tasks", response_model=schemas.TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(task_in: schemas.TaskCreate, db: Session = Depends(get_db),
                user: CurrentUser = Depends(get_current_user)):
    # Владелец из токена. Задача в проекте принадлежит владельцу проекта
    # (admin, создавая задачу в чужом проекте, не становится её владельцем).
    # is not None: project_id=0 тоже проверяется, иначе на PostgreSQL 500 от внешнего ключа
    owner_id = user.id
    if task_in.project_id is not None:
        owner_id = get_owned_project(db, task_in.project_id, user).owner_id
    task = crud.create_task(db, task_in, owner_id=owner_id)
    logger.info(f"Task created: id={task.id}, project_id={task.project_id}, owner_id={task.owner_id}")
    return task

@router.get("/tasks", response_model=List[schemas.TaskRead])
def list_tasks(skip: int = 0, limit: int = 100,
               project_id: Optional[int] = Query(None), status_filter: Optional[models.TaskStatus] = Query(None, alias="status"),
               db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    return crud.list_tasks(db, skip=skip, limit=limit, project_id=project_id, status=status_filter,
                           owner_id=_owner_scope(user))

@router.get("/tasks/{task_id}", response_model=schemas.TaskRead)
def get_task(task_id: int, db: Session = Depends(get_db),
             user: CurrentUser = Depends(get_current_user)):
    return get_owned_task(db, task_id, user)

@router.put("/tasks/{task_id}", response_model=schemas.TaskRead)
def update_task(task_id: int, update_in: schemas.TaskUpdate, db: Session = Depends(get_db),
                user: CurrentUser = Depends(get_current_user)):
    logger.info(f"Updating task: id={task_id}, update={update_in.dict()}")
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
def delete_task(task_id: int, db: Session = Depends(get_db),
                user: CurrentUser = Depends(get_current_user)):
    t = get_owned_task(db, task_id, user)
    crud.delete_task(db, t)
    logger.info(f"Task deleted: id={task_id}")
    return {}

# convenience change-status endpoint
@router.post("/tasks/{task_id}/status", response_model=schemas.TaskRead)
def change_status(task_id: int, status_in: dict, db: Session = Depends(get_db),
                  user: CurrentUser = Depends(get_current_user)):
    logger.info(f"Changing task status: id={task_id}, new_status={status_in}")
    t = get_owned_task(db, task_id, user)
    # expect {"status":"in_progress"}
    new_status = status_in.get("status")
    if new_status is None:
        raise HTTPException(status_code=400, detail="Missing status")
    try:
        t.status = models.TaskStatus(new_status)
    except Exception as e:
        logger.error(f"Invalid status: {new_status}, error: {e}")
        raise HTTPException(status_code=400, detail="Invalid status")
    db.add(t)
    db.commit()
    db.refresh(t)
    logger.info(f"Task status changed: id={task_id}, new_status={t.status}")
    return t

# --- Statistics ---
@router.get("/statistics/users")
async def get_users_statistics(user: CurrentUser = Depends(require_admin)):
    """Статистика по пользователям: кол-во задач и среднее время (только admin)"""
    logger.info("Getting users statistics")

    # time-service сам проверяет токен, поэтому пробрасываем Authorization пользователя
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.TIME_SERVICE_URL}/api/time/statistics/users",
                headers={"Authorization": user.authorization},
                timeout=10.0,
            )
    except httpx.HTTPError as e:
        logger.error(f"Error getting statistics from time-service: {e}")
        raise HTTPException(status_code=502, detail="Time service unavailable")

    if response.status_code != 200:
        logger.error(f"Failed to get statistics from time-service: {response.status_code}")
        raise HTTPException(status_code=502, detail="Failed to get statistics")

    stats = response.json()
    logger.info(f"Statistics retrieved: {len(stats)} users")
    return stats
