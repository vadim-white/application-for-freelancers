from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session
from . import schemas, crud, models
from .deps import get_db
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

def get_user_from_token(request: Request) -> dict:
    """Извлекает информацию о пользователе из JWT токена"""
    from jose import jwt, JWTError
    from .core.config import settings
    
    auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth_header:
        return {"id": None, "role": None}
    
    try:
        scheme, token = auth_header.split()
        if scheme.lower() != "bearer":
            return {"id": None, "role": None}
        
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"verify_exp": False}
        )
        return {
            "id": int(payload.get("sub")),
            "role": payload.get("role", "user")
        }
    except (ValueError, JWTError, KeyError):
        return {"id": None, "role": None}

# --- Projects ---
@router.post("/projects", response_model=schemas.ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(project_in: schemas.ProjectCreate, request: Request, db: Session = Depends(get_db)):
    # Проверка доступа - только admin может создавать проекты
    user = get_user_from_token(request)
    if user["role"] != "admin":
        logger.warning(f"Unauthorized project creation attempt by user {user['id']}")
        raise HTTPException(status_code=403, detail="Only admins can create projects")
    
    project = crud.create_project(db, project_in)
    logger.info(f"Project created: id={project.id}")
    return project

@router.get("/projects", response_model=List[schemas.ProjectRead])
def list_projects(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.list_projects(db, skip=skip, limit=limit)

@router.get("/projects/{project_id}", response_model=schemas.ProjectRead)
def get_project(project_id: int, db: Session = Depends(get_db)):
    p = crud.get_project(db, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return p

@router.put("/projects/{project_id}", response_model=schemas.ProjectRead)
def update_project(project_id: int, update_in: schemas.ProjectUpdate, request: Request, db: Session = Depends(get_db)):
    # Проверка доступа - только admin может обновлять проекты
    user = get_user_from_token(request)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only admins can update projects")
    
    p = crud.get_project(db, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return crud.update_project(db, p, update_in)

@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: int, request: Request, db: Session = Depends(get_db)):
    # Проверка доступа - только admin может удалять проекты
    user = get_user_from_token(request)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only admins can delete projects")
    
    p = crud.get_project(db, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    crud.delete_project(db, p)
    logger.info(f"Project deleted: id={project_id}")
    return {}

# --- Tasks ---
@router.post("/tasks", response_model=schemas.TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(task_in: schemas.TaskCreate, db: Session = Depends(get_db)):
    # optional: validate project exists
    if task_in.project_id:
        proj = crud.get_project(db, task_in.project_id)
        if not proj:
            raise HTTPException(status_code=400, detail="Project does not exist")
    task = crud.create_task(db, task_in)
    logger.info(f"Task created: id={task.id}, project_id={task.project_id}")
    return task

@router.get("/tasks", response_model=List[schemas.TaskRead])
def list_tasks(skip: int = 0, limit: int = 100,
               project_id: Optional[int] = Query(None), status_filter: Optional[models.TaskStatus] = Query(None, alias="status"),
               db: Session = Depends(get_db)):
    return crud.list_tasks(db, skip=skip, limit=limit, project_id=project_id, status=status_filter)

@router.get("/tasks/{task_id}", response_model=schemas.TaskRead)
def get_task(task_id: int, db: Session = Depends(get_db)):
    t = crud.get_task(db, task_id)
    if not t:
        raise HTTPException(status_code=404, detail="Task not found")
    return t

@router.put("/tasks/{task_id}", response_model=schemas.TaskRead)
def update_task(task_id: int, update_in: schemas.TaskUpdate, db: Session = Depends(get_db)):
    logger.info(f"Updating task: id={task_id}, update={update_in.dict()}")
    t = crud.get_task(db, task_id)
    if not t:
        raise HTTPException(status_code=404, detail="Task not found")
    result = crud.update_task(db, t, update_in)
    logger.info(f"Task updated: id={task_id}, new_status={result.status}")
    return result

@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, db: Session = Depends(get_db)):
    t = crud.get_task(db, task_id)
    if not t:
        raise HTTPException(status_code=404, detail="Task not found")
    crud.delete_task(db, t)
    logger.info(f"Task deleted: id={task_id}")
    return {}

# convenience change-status endpoint
@router.post("/tasks/{task_id}/status", response_model=schemas.TaskRead)
def change_status(task_id: int, status_in: dict, db: Session = Depends(get_db)):
    logger.info(f"Changing task status: id={task_id}, new_status={status_in}")
    t = crud.get_task(db, task_id)
    if not t:
        raise HTTPException(status_code=404, detail="Task not found")
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
async def get_users_statistics(db: Session = Depends(get_db)):
    """Статистика по пользователям: кол-во задач и среднее время"""
    import httpx
    from .core.config import settings
    
    logger.info("Getting users statistics")
    
    try:
        # Получаем статистику из time-service
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.TIME_SERVICE_URL}/api/time/statistics/users",
                timeout=10.0
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to get statistics from time-service: {response.status_code}")
                raise HTTPException(status_code=500, detail="Failed to get statistics")
            
            stats = response.json()
            logger.info(f"Statistics retrieved: {len(stats)} users")
            return stats
            
    except Exception as e:
        logger.error(f"Error getting statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))
