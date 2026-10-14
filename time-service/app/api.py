from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from . import schemas, crud
from .db import SessionLocal
from jose import JWTError
import logging

logger = logging.getLogger(__name__)

# если в time-service есть core.security.decode_token и config — используем их
try:
    from .core.security import decode_token
    from .core.config import settings
    _have_jwt_tools = True
except Exception as e:
    logger.warning(f"JWT tools not available: {e}")
    _have_jwt_tools = False

router = APIRouter()

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Projects
@router.post("/projects", response_model=schemas.ProjectRead)
def create_project(project_in: schemas.ProjectCreate, db: Session = Depends(get_db)):
    return crud.create_project(db, project_in)

@router.get("/projects", response_model=List[schemas.ProjectRead])
def list_projects(db: Session = Depends(get_db)):
    return crud.get_projects(db)

# Time entries
@router.post("/time-entries", response_model=schemas.TimeEntryRead)
def create_entry(entry_in: schemas.TimeEntryCreate, request: Request, db: Session = Depends(get_db)):
    """
    Создает запись о затраченном времени.
    Если client не присылает user_id, попытаемся взять user id из Authorization Bearer JWT (sub).
    Если декодирование токена недоступно или не удалось — user_id останется None (допустимо).
    """
    logger.info(f"Creating time entry: task_id={entry_in.task_id}, minutes={entry_in.minutes}, user_id={entry_in.user_id}")
    
    payload_user = None
    if entry_in.user_id is None and _have_jwt_tools:
        auth = request.headers.get("authorization") or request.headers.get("Authorization")
        if auth:
            try:
                parts = auth.split()
                if len(parts) == 2:
                    scheme, token = parts
                    if scheme.lower() == "bearer":
                        payload = decode_token(token)
                        sub = payload.get("sub")
                        if sub is not None:
                            try:
                                payload_user = int(sub)
                                logger.info(f"Extracted user_id from token: {payload_user}")
                            except Exception as e:
                                logger.warning(f"Failed to extract user_id from token: {e}")
            except (ValueError, JWTError) as e:
                logger.warning(f"Failed to decode token: {e}")

    # build a new TimeEntryCreate object with resolved user_id
    data = entry_in.dict()
    if data.get("user_id") is None and payload_user is not None:
        data["user_id"] = payload_user

    # if user_id still missing – it's allowed now (nullable)
    try:
        te = schemas.TimeEntryCreate(**data)
    except Exception as e:
        logger.error(f"Invalid payload: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid payload: {e}")

    try:
        result = crud.create_time_entry(db, te)
        logger.info(f"Time entry created successfully: id={result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/time-entries", response_model=List[schemas.TimeEntryRead])
def list_entries(task_id: int = None, user_id: int = None, db: Session = Depends(get_db)):
    return crud.get_time_entries(db, task_id=task_id, user_id=user_id)

# Statistics
@router.get("/statistics/users")
def get_users_statistics(db: Session = Depends(get_db)):
    """
    Получает статистику по пользователям:
    - email, full_name из token
    - task_count: кол-во время-записей (задач выполненных)
    - avg_minutes: среднее время на задачу в минутах
    """
    logger.info("Getting users statistics")
    
    try:
        # Группируем по user_id и получаем статистику
        from . import models
        
        stats = db.query(
            models.TimeEntry.user_id,
            func.count(models.TimeEntry.id).label('task_count'),
            func.avg(models.TimeEntry.minutes).label('avg_minutes')
        ).filter(
            models.TimeEntry.user_id != None
        ).group_by(
            models.TimeEntry.user_id
        ).all()
        
        # Преобразуем в список словарей
        result = []
        for stat in stats:
            result.append({
                'user_id': stat.user_id,
                'email': f'user_{stat.user_id}@example.com',  # placeholder
                'full_name': f'User {stat.user_id}',  # placeholder
                'task_count': stat.task_count,
                'avg_minutes': round(float(stat.avg_minutes)) if stat.avg_minutes else 0
            })
        
        logger.info(f"Users statistics retrieved: {len(result)} users")
        return result
        
    except Exception as e:
        logger.error(f"Error getting statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))
