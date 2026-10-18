import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import crud, schemas
from .core.auth import CurrentUser, get_current_user, require_admin
from .db import SessionLocal

logger = logging.getLogger(__name__)

# Все эндпоинты требуют валидный access-токен (401 без него)
router = APIRouter(dependencies=[Depends(get_current_user)])


# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Time entries
@router.post("/time-entries", response_model=schemas.TimeEntryRead)
def create_entry(
    entry_in: schemas.TimeEntryCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """Создает запись о затраченном времени. user_id берётся только из токена."""
    logger.info(
        f"Creating time entry: task_id={entry_in.task_id}, minutes={entry_in.minutes}, "
        f"user_id={user.id}"
    )
    try:
        result = crud.create_time_entry(db, entry_in, user_id=user.id)
        logger.info(f"Time entry created successfully: id={result.id}")
        return result
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/time-entries", response_model=list[schemas.TimeEntryRead])
def list_entries(
    task_id: int | None = None,
    user_id: int | None = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """Пользователь видит только свои записи, admin — все (с фильтром user_id)."""
    if not user.is_admin:
        if user_id is not None and user_id != user.id:
            raise HTTPException(status_code=403, detail="Cannot view other users' time entries")
        user_id = user.id
    return crud.get_time_entries(db, task_id=task_id, user_id=user_id)


# Statistics
@router.get("/statistics/users")
def get_users_statistics(db: Session = Depends(get_db), user: CurrentUser = Depends(require_admin)):
    """
    Получает статистику по пользователям (только admin):
    - email, full_name из token
    - task_count: кол-во время-записей (задач выполненных)
    - avg_minutes: среднее время на задачу в минутах
    """
    logger.info("Getting users statistics")

    try:
        # Группируем по user_id и получаем статистику
        from . import models

        stats = (
            db.query(
                models.TimeEntry.user_id,
                func.count(models.TimeEntry.id).label("task_count"),
                func.avg(models.TimeEntry.minutes).label("avg_minutes"),
            )
            .group_by(models.TimeEntry.user_id)
            .all()
        )

        # Преобразуем в список словарей
        result = []
        for stat in stats:
            result.append(
                {
                    "user_id": stat.user_id,
                    "email": f"user_{stat.user_id}@example.com",  # placeholder
                    "full_name": f"User {stat.user_id}",  # placeholder
                    "task_count": stat.task_count,
                    "avg_minutes": round(float(stat.avg_minutes)) if stat.avg_minutes else 0,
                }
            )

        logger.info(f"Users statistics retrieved: {len(result)} users")
        return result

    except Exception as e:
        logger.error(f"Error getting statistics: {e}")
        raise HTTPException(status_code=500, detail="Failed to get statistics") from e
