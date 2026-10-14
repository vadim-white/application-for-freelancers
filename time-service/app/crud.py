from sqlalchemy.orm import Session
from . import models, schemas
import logging

logger = logging.getLogger(__name__)

def get_project(db: Session, project_id: int):
    return db.query(models.Project).filter(models.Project.id == project_id).first()

def get_projects(db: Session):
    return db.query(models.Project).all()

def create_project(db: Session, project_in: schemas.ProjectCreate):
    project = models.Project(**project_in.dict())
    db.add(project)
    db.commit()
    db.refresh(project)
    return project

def create_time_entry(db: Session, entry_in: schemas.TimeEntryCreate):
    # validate minutes
    logger.info(f"Creating time entry: task_id={entry_in.task_id}, minutes={entry_in.minutes}")
    
    if entry_in.minutes is None or entry_in.minutes <= 0:
        logger.error(f"Invalid minutes value: {entry_in.minutes}")
        raise ValueError("Invalid minutes value; must be > 0")

    data = entry_in.dict()
    # allow user_id to be None
    entry = models.TimeEntry(**data)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    logger.info(f"Time entry created successfully: id={entry.id}")
    return entry

def get_time_entries(db: Session, task_id: int = None, user_id: int = None):
    query = db.query(models.TimeEntry)
    if task_id:
        query = query.filter(models.TimeEntry.task_id == task_id)
    if user_id:
        query = query.filter(models.TimeEntry.user_id == user_id)
    return query.all()
