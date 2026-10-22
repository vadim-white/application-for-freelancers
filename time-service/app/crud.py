import logging
import math
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import models, schemas

logger = logging.getLogger(__name__)


class TimerConflict(Exception):
    """Параллельный старт другой реплики дважды занял слот идущего таймера."""


def now() -> datetime:
    return datetime.now(UTC)


def create_time_entry(db: Session, entry_in: schemas.TimeEntryCreate, user_id: int):
    logger.info(f"Creating time entry: task_id={entry_in.task_id}, minutes={entry_in.minutes}")

    if entry_in.minutes is None or entry_in.minutes <= 0:
        logger.error(f"Invalid minutes value: {entry_in.minutes}")
        raise ValueError("Invalid minutes value; must be > 0")

    stopped_at = now()
    entry = models.TimeEntry(
        **entry_in.model_dump(),
        user_id=user_id,
        started_at=stopped_at - timedelta(minutes=entry_in.minutes),
        stopped_at=stopped_at,
        duration_seconds=entry_in.minutes * 60,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    logger.info(f"Time entry created successfully: id={entry.id}")
    return entry


def get_time_entries(db: Session, task_id: int = None, user_id: int = None):
    query = db.query(models.TimeEntry)
    if task_id is not None:
        query = query.filter(models.TimeEntry.task_id == task_id)
    if user_id is not None:
        query = query.filter(models.TimeEntry.user_id == user_id)
    return query.all()


def get_running(db: Session, user_id: int, lock: bool = False) -> models.TimeEntry | None:
    query = select(models.TimeEntry).where(
        models.TimeEntry.user_id == user_id, text(models.RUNNING)
    )
    if lock:
        query = query.with_for_update()
    return db.scalars(query).first()


def close_entry(entry: models.TimeEntry, at: datetime) -> None:
    # часы реплик могут расходиться: конец не раньше начала
    entry.stopped_at = max(at, entry.started_at)
    entry.duration_seconds = math.floor((entry.stopped_at - entry.started_at).total_seconds())
    entry.minutes = max(1, math.ceil(entry.duration_seconds / 60))


def _start_once(db: Session, user_id: int, timer_in: schemas.TimerStart):
    at = now()
    running = get_running(db, user_id, lock=True)
    if running is not None and running.task_id == timer_in.task_id:
        db.rollback()
        return running, None, False
    if running is not None:
        close_entry(running, at)
        # UPDATE раньше INSERT явно, а не по порядку unit of work: иначе — уникальный индекс
        db.flush()
    # minutes = 1: старые поды в окне выкатки валидируют minutes > 0 при чтении
    entry = models.TimeEntry(
        task_id=timer_in.task_id,
        user_id=user_id,
        description=timer_in.description,
        started_at=at,
        minutes=1,
    )
    db.add(entry)
    db.commit()
    return entry, running, True


def start_timer(db: Session, user_id: int, timer_in: schemas.TimerStart):
    """(entry, stopped, created). Один повтор: второй старт выигрывает у параллельного первого."""
    for attempt in range(2):
        try:
            return _start_once(db, user_id, timer_in)
        except IntegrityError:
            db.rollback()
            logger.warning(f"Timer start conflict for user_id={user_id}, attempt {attempt + 1}")
    raise TimerConflict


def stop_timer(db: Session, user_id: int) -> models.TimeEntry | None:
    running = get_running(db, user_id, lock=True)
    if running is None:
        db.rollback()
        return None
    close_entry(running, now())
    db.commit()
    return running
