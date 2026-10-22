from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import AwareDatetime
from sqlalchemy.orm import Session

from . import crud, schemas
from .core.auth import CurrentUser, get_current_user, require_admin
from .deps import get_db
from .task_client import fetch_usable_task, get_task_client

# Все эндпоинты требуют валидный access-токен (401 без него)
router = APIRouter(dependencies=[Depends(get_current_user)])


# Time entries
async def checked_entry_create(
    entry_in: schemas.TimeEntryCreate,
    client: httpx.AsyncClient = Depends(get_task_client),
    user: CurrentUser = Depends(get_current_user),
) -> schemas.TimeEntryCreate:
    # асинхронная зависимость, как у старта таймера: task вызывается до тела эндпоинта и до базы
    await fetch_usable_task(client, entry_in.task_id, user.authorization)
    return entry_in


async def checked_entry_update(
    entry_in: schemas.TimeEntryUpdate,
    client: httpx.AsyncClient = Depends(get_task_client),
    user: CurrentUser = Depends(get_current_user),
) -> schemas.TimeEntryUpdate:
    # задачу проверяем, только если task_id есть в теле
    if "task_id" in entry_in.model_fields_set:
        await fetch_usable_task(client, entry_in.task_id, user.authorization)
    return entry_in


def get_own_entry(db: Session, entry_id: int, user: CurrentUser):
    """Своя запись; у admin — любая. Чужая неотличима от несуществующей (404)."""
    entry = crud.get_entry(db, entry_id, None if user.is_admin else user.id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Time entry not found")
    return entry


@router.post("/time-entries", response_model=schemas.TimeEntryRead, status_code=201)
def create_entry(
    entry_in: schemas.TimeEntryCreate = Depends(checked_entry_create),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """Ручная запись. user_id берётся только из токена."""
    try:
        return crud.create_time_entry(db, entry_in, user_id=user.id)
    except crud.InvalidEntry as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get("/time-entries", response_model=schemas.TimeEntryList)
def list_entries(
    task_id: int | None = None,
    user_id: int | None = None,
    from_: AwareDatetime | None = Query(None, alias="from"),
    to: AwareDatetime | None = None,
    sort: Literal["started_at", "-started_at"] = "-started_at",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """Пользователь видит только свои записи, admin — все (с фильтром user_id)."""
    if not user.is_admin:
        if user_id is not None and user_id != user.id:
            raise HTTPException(status_code=403, detail="Cannot view other users' time entries")
        user_id = user.id
    items, total = crud.list_time_entries(
        db,
        user_id=user_id,
        task_id=task_id,
        from_=from_,
        to=to,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.patch("/time-entries/{entry_id}", response_model=schemas.TimeEntryRead)
def update_entry(
    entry_id: int,
    entry_in: schemas.TimeEntryUpdate = Depends(checked_entry_update),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    entry = get_own_entry(db, entry_id, user)
    try:
        return crud.update_time_entry(db, entry, entry_in)
    except crud.InvalidEntry as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except crud.LegacyEntry as e:
        raise HTTPException(status_code=409, detail="Entry is not migrated yet, retry later") from e


@router.delete("/time-entries/{entry_id}", status_code=204)
def delete_entry(
    entry_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
):
    """Удаляет запись, в том числе идущую (таймер при этом останавливается)."""
    crud.delete_time_entry(db, get_own_entry(db, entry_id, user))


# Timer: у каждого, включая admin, — только свой таймер
@router.get("/timer", response_model=schemas.TimerState)
def get_timer(db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    return {"entry": crud.get_running(db, user.id), "server_time": crud.now()}


async def checked_timer_start(
    timer_in: schemas.TimerStart,
    client: httpx.AsyncClient = Depends(get_task_client),
    user: CurrentUser = Depends(get_current_user),
) -> schemas.TimerStart:
    # Асинхронная зависимость: task вызывается в event loop до тела эндпоинта и до транзакции;
    # эндпоинт остаётся синхронным (база — в пуле потоков), соединение с базой при вызове не занято
    await fetch_usable_task(client, timer_in.task_id, user.authorization)
    return timer_in


@router.post("/timer/start", response_model=schemas.TimerStarted)
def start_timer(
    response: Response,
    timer_in: schemas.TimerStart = Depends(checked_timer_start),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """Новая запись — 201 (идущая на другой задаче закрывается), та же задача уже идёт — 200.

    Задача ушла в архив — 409 даже на ту же идущую: проверка раньше, идущую запись она не трогает.
    """
    try:
        entry, stopped, created = crud.start_timer(db, user.id, timer_in)
    except crud.TimerConflict as e:
        raise HTTPException(status_code=409, detail="Timer start conflict, retry") from e
    response.status_code = 201 if created else 200
    return {"entry": entry, "stopped": stopped, "server_time": crud.now()}


@router.post("/timer/stop", response_model=schemas.TimerStopped)
def stop_timer(db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    return {"stopped": crud.stop_timer(db, user.id), "server_time": crud.now()}


# Statistics
@router.get("/statistics/users", response_model=list[schemas.UserStatistics])
def get_users_statistics(db: Session = Depends(get_db), user: CurrentUser = Depends(require_admin)):
    """Статистика по закрытым записям каждого пользователя (только admin)."""
    return crud.users_statistics(db)
