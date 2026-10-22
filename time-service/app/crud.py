import logging
import math
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import models, schemas

logger = logging.getLogger(__name__)


class TimerConflict(Exception):
    """Параллельный старт другой реплики дважды занял слот идущего таймера."""


def now() -> datetime:
    return datetime.now(UTC)


class InvalidEntry(Exception):
    """Время записи не сходится: отдаётся как 422."""


# часы реплик и клиента расходятся: небольшое «будущее» не ошибка
FUTURE_TOLERANCE = timedelta(minutes=1)


def check_times(started_at: datetime, stopped_at: datetime | None, at: datetime) -> None:
    if started_at > at + FUTURE_TOLERANCE:
        raise InvalidEntry("started_at is in the future")
    if stopped_at is None:
        return
    if stopped_at < started_at:
        raise InvalidEntry("stopped_at must not be earlier than started_at")
    if stopped_at > at + FUTURE_TOLERANCE:
        raise InvalidEntry("stopped_at is in the future")


def create_time_entry(db: Session, entry_in: schemas.TimeEntryCreate, user_id: int):
    check_times(entry_in.started_at, entry_in.stopped_at, now())
    entry = models.TimeEntry(**entry_in.model_dump(), user_id=user_id)
    set_duration(entry)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def get_entry(db: Session, entry_id: int, user_id: int | None) -> models.TimeEntry | None:
    """user_id=None — без ограничения по владельцу (admin)."""
    entry = db.get(models.TimeEntry, entry_id)
    if entry is None or (user_id is not None and entry.user_id != user_id):
        return None
    return entry


def update_time_entry(db: Session, entry: models.TimeEntry, data: schemas.TimeEntryUpdate):
    fields = data.model_fields_set
    if "description" in fields:
        entry.description = data.description
    if "task_id" in fields:
        entry.task_id = data.task_id
    if fields & {"started_at", "stopped_at"}:
        if entry.stopped_at is None and "stopped_at" in fields:
            raise InvalidEntry("Cannot set stopped_at on a running entry")
        started_at = data.started_at if "started_at" in fields else entry.started_at
        stopped_at = data.stopped_at if "stopped_at" in fields else entry.stopped_at
        check_times(started_at, stopped_at, now())
        entry.started_at, entry.stopped_at = started_at, stopped_at
        if stopped_at is not None:
            set_duration(entry)
    db.commit()
    db.refresh(entry)
    return entry


def delete_time_entry(db: Session, entry: models.TimeEntry) -> None:
    db.delete(entry)
    db.commit()


def list_time_entries(
    db: Session,
    *,
    user_id: int | None,
    task_id: int | None,
    from_: datetime | None,
    to: datetime | None,
    sort: str,
    limit: int,
    offset: int,
):
    """(items, total). from включительно, to не включительно."""
    entry = models.TimeEntry
    conditions = []
    if user_id is not None:
        conditions.append(entry.user_id == user_id)
    if task_id is not None:
        conditions.append(entry.task_id == task_id)
    if from_ is not None:
        conditions.append(entry.started_at >= from_)
    if to is not None:
        conditions.append(entry.started_at < to)
    descending = sort.startswith("-")
    started = entry.started_at.desc() if descending else entry.started_at.asc()
    order = [started, entry.id.desc() if descending else entry.id.asc()]
    total = db.scalar(select(func.count()).select_from(entry).where(*conditions))
    items = db.scalars(
        select(entry).where(*conditions).order_by(*order).limit(limit).offset(offset)
    )
    return list(items), total


def users_statistics(db: Session) -> list[dict]:
    """По закрытым записям: у идущих duration_seconds ещё нет."""
    entry = models.TimeEntry
    rows = db.execute(
        select(
            entry.user_id,
            func.count(entry.id),
            func.count(entry.task_id.distinct()),
            func.sum(entry.duration_seconds),
        )
        .where(entry.duration_seconds.is_not(None))
        .group_by(entry.user_id)
        .order_by(entry.user_id)
    )
    return [
        {
            "user_id": user_id,
            "entries_count": entries,
            "tasks_count": tasks,
            "total_seconds": total,
            "avg_seconds_per_task": round(total / tasks),
        }
        for user_id, entries, tasks, total in rows
    ]


def get_running(db: Session, user_id: int, lock: bool = False) -> models.TimeEntry | None:
    query = select(models.TimeEntry).where(
        models.TimeEntry.user_id == user_id, text(models.RUNNING)
    )
    if lock:
        query = query.with_for_update()
    return db.scalars(query).first()


def set_duration(entry: models.TimeEntry) -> None:
    entry.duration_seconds = math.floor((entry.stopped_at - entry.started_at).total_seconds())


def close_entry(entry: models.TimeEntry, at: datetime) -> None:
    # часы реплик могут расходиться: конец не раньше начала
    entry.stopped_at = max(at, entry.started_at)
    set_duration(entry)


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
    entry = models.TimeEntry(
        task_id=timer_in.task_id,
        user_id=user_id,
        description=timer_in.description,
        started_at=at,
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
