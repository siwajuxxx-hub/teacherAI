import json
import logging
from datetime import date, time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field

from app.database import get_data_session
from app.models.data_models import Schedule, ScheduleType, ScheduleSource
from app.models.auth_models import User
from app.schemas.data_schemas import (
    ScheduleCreate, ScheduleBatchCreate, ScheduleUpdate, ScheduleOut,
)
from app.security import get_current_user, require_admin_or_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/schedule", tags=["Расписание"])


def _parse_time(t: str) -> time:
    try:
        parts = str(t).strip().replace(".", ":").split(":")
        return time(int(parts[0]), int(parts[1]))
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Неверный формат времени: {t}. Ожидается HH:MM")


def _parse_date(s) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Неверная дата: {s} (ожидается YYYY-MM-DD)")


def _schedule_to_out(s: Schedule) -> ScheduleOut:
    return ScheduleOut(
        id=s.id,
        user_id=s.user_id,
        title=s.title,
        day_of_week=s.day_of_week,
        event_date=s.event_date.isoformat() if s.event_date else None,
        weeks=s.weeks or None,
        start_time=s.start_time.strftime("%H:%M"),
        end_time=s.end_time.strftime("%H:%M"),
        group_name=s.group_name,
        room=s.room,
        type=s.type,
        source=s.source,
        created_by=s.created_by,
        created_at=s.created_at,
    )


async def _list_schedule(db: AsyncSession, user_id: str,
                         dt_from: date | None, dt_to: date | None) -> list[ScheduleOut]:
    """Записи преподавателя. с from/to: датированные в диапазоне + ВСЕ недельные
    шаблоны (они применимы к любой неделе)."""
    r = await db.execute(
        select(Schedule).where(Schedule.user_id == user_id)
        .order_by(Schedule.day_of_week, Schedule.start_time))
    rows = r.scalars().all()
    out = []
    for s in rows:
        if dt_from and s.event_date and not (dt_from <= s.event_date <= (dt_to or dt_from)):
            continue
        out.append(_schedule_to_out(s))
    return out


@router.get("/my", response_model=list[ScheduleOut])
async def get_my_schedule(
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    db: AsyncSession = Depends(get_data_session),
    current_user: User = Depends(get_current_user),
):
    return await _list_schedule(db, current_user.id, _parse_date(date_from), _parse_date(date_to))


@router.get("/user/{user_id}", response_model=list[ScheduleOut])
async def get_user_schedule(
    user_id: str,
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_data_session),
    _: User = Depends(require_admin_or_manager),
):
    """Расписание другого преподавателя (для управляющего/админа)."""
    return await _list_schedule(db, user_id, _parse_date(date_from), _parse_date(date_to))


@router.post("/", response_model=ScheduleOut, status_code=status.HTTP_201_CREATED)
async def create_schedule(
    body: ScheduleCreate,
    db: AsyncSession = Depends(get_data_session),
    current_user: User = Depends(get_current_user),
):
    user_id = body.user_id or current_user.id
    if current_user.role == "teacher" and user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Вы можете добавлять расписание только себе")

    ed = _parse_date(body.event_date)
    dow = body.day_of_week
    if dow is None:
        if ed is None:
            raise HTTPException(status_code=400, detail="Нужен день недели или конкретная дата")
        dow = ed.weekday()

    schedule = Schedule(
        user_id=user_id,
        title=body.title,
        day_of_week=dow,
        start_time=_parse_time(body.start_time),
        end_time=_parse_time(body.end_time),
        group_name=body.group_name,
        room=body.room,
        type=body.type,
        source=ScheduleSource.MANAGER if (user_id != current_user.id
                                          and current_user.role in ("admin", "manager"))
               else body.source,
        created_by=current_user.id,
        event_date=ed,
        weeks=(body.weeks or None),
    )
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)
    return _schedule_to_out(schedule)


@router.post("/batch", response_model=list[ScheduleOut], status_code=status.HTTP_201_CREATED)
async def batch_create_schedule(
    body: ScheduleBatchCreate,
    db: AsyncSession = Depends(get_data_session),
    current_user: User = Depends(get_current_user),
):
    """Массовое добавление (старый путь ручного импорта). Дубли пропускаются."""
    target_user_id = body.user_id or current_user.id
    if current_user.role == "teacher" and target_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Вы можете добавлять расписание только себе")

    from app.services.schedule_dedup import DuplicateTracker
    tracker = DuplicateTracker()
    await tracker.prime(db, target_user_id)

    created = []
    for item in body.items:
        ed = _parse_date(item.event_date)
        dow = item.day_of_week if item.day_of_week is not None else (ed.weekday() if ed else 0)
        candidate = {
            "title": item.title,
            "day_of_week": dow,
            "start_time": item.start_time,
            "end_time": item.end_time,
            "group_name": item.group_name,
            "event_date": item.event_date or "",
            "weeks": item.weeks or "",
        }
        if tracker.is_duplicate(target_user_id, candidate):
            continue
        schedule = Schedule(
            user_id=target_user_id,
            title=item.title,
            day_of_week=dow,
            start_time=_parse_time(item.start_time),
            end_time=_parse_time(item.end_time),
            group_name=item.group_name,
            room=item.room,
            type=item.type,
            source=ScheduleSource.PDF_IMPORT,
            created_by=current_user.id,
            event_date=ed,
            weeks=item.weeks or None,
        )
        db.add(schedule)
        created.append(schedule)

    await db.commit()
    for s in created:
        await db.refresh(s)
    return [_schedule_to_out(s) for s in created]


@router.put("/{schedule_id}", response_model=ScheduleOut)
async def update_schedule(
    schedule_id: str,
    body: ScheduleUpdate,
    db: AsyncSession = Depends(get_data_session),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Schedule).where(Schedule.id == schedule_id))
    schedule = result.scalar_one_or_none()
    if schedule is None:
        raise HTTPException(status_code=404, detail="Запись расписания не найдена")

    is_mgr = current_user.role in ("admin", "manager")
    if not is_mgr and schedule.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Вы можете редактировать только своё расписание")

    data = body.model_dump(exclude_unset=True)

    if data.get("user_id") and data["user_id"] != schedule.user_id:
        if not is_mgr:
            raise HTTPException(status_code=403, detail="Переносить пару на другого может только управляющий")
        from app.database import AuthSessionLocal
        async with AuthSessionLocal() as adb:
            target = await adb.get(User, data["user_id"])
        if target is None:
            raise HTTPException(status_code=400, detail="Пользователь-получатель не найден")
        schedule.user_id = target.id
        schedule.source = ScheduleSource.MANAGER  # перенесённая менеджером пара защищена от учителя

    if "event_date" in data:
        if data["event_date"] == "":
            schedule.event_date = None
        else:
            schedule.event_date = _parse_date(data["event_date"])
            if "day_of_week" not in data and schedule.event_date:
                schedule.day_of_week = schedule.event_date.weekday()

    if "start_time" in data and data["start_time"]:
        data["start_time"] = _parse_time(data["start_time"])
    if "end_time" in data and data["end_time"]:
        data["end_time"] = _parse_time(data["end_time"])

    for key in ("title", "day_of_week", "weeks", "start_time", "end_time",
                "group_name", "room", "type"):
        if key in data and data[key] is not None:
            setattr(schedule, key, data[key])

    await db.commit()
    await db.refresh(schedule)
    return _schedule_to_out(schedule)


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(
    schedule_id: str,
    db: AsyncSession = Depends(get_data_session),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Schedule).where(Schedule.id == schedule_id))
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Запись расписания не найдена")

    is_mgr = current_user.role in ("admin", "manager")
    if not is_mgr and schedule.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Вы можете удалять только своё расписание")
    # пару, заведённую управляющим другому преподавателю, учитель сам не трогает
    if current_user.role == "teacher" and schedule.source == ScheduleSource.MANAGER:
        raise HTTPException(status_code=403, detail="Эту запись добавил управляющий — обратитесь к нему")

    await db.delete(schedule)
    await db.commit()
