import logging

from sqlalchemy.orm import Session

from . import models, schemas

logger = logging.getLogger(__name__)


def create_time_entry(db: Session, entry_in: schemas.TimeEntryCreate, user_id: int):
    # validate minutes
    logger.info(f"Creating time entry: task_id={entry_in.task_id}, minutes={entry_in.minutes}")

    if entry_in.minutes is None or entry_in.minutes <= 0:
        logger.error(f"Invalid minutes value: {entry_in.minutes}")
        raise ValueError("Invalid minutes value; must be > 0")

    entry = models.TimeEntry(**entry_in.dict(), user_id=user_id)
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
