from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import time
from typing import Optional

from app.database import get_data_session
from app.models.data_models import Schedule, ScheduleType, ScheduleSource
from app.models.auth_models import User
from app.schemas.data_schemas import (
    ScheduleCreate, ScheduleBatchCreate, ScheduleUpdate, ScheduleOut,
)
from app.security import get_current_user, require_admin_or_manager

router = APIRouter(prefix="/api/schedule", tags=["Расписание"])


def _parse_time(t: str) -> time:
    try:
        parts = t.strip().split(":")
        return time(int(parts[0]), int(parts[1]))
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Неверный формат времени: {t}. Ожидается HH:MM")


def _schedule_to_out(s: Schedule) -> ScheduleOut:
    return ScheduleOut(
        id=s.id,
        user_id=s.user_id,
        title=s.title,
        day_of_week=s.day_of_week,
        start_time=s.start_time.strftime("%H:%M"),
        end_time=s.end_time.strftime("%H:%M"),
        group_name=s.group_name,
        room=s.room,
        type=s.type,
        source=s.source,
        created_by=s.created_by,
        created_at=s.created_at,
    )


@router.get("/my", response_model=list[ScheduleOut])
async def get_my_schedule(
    db: AsyncSession = Depends(get_data_session),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Schedule)
        .where(Schedule.user_id == current_user.id)
        .order_by(Schedule.day_of_week, Schedule.start_time)
    )
    return [_schedule_to_out(s) for s in result.scalars().all()]


@router.get("/user/{user_id}", response_model=list[ScheduleOut])
async def get_user_schedule(
    user_id: str,
    db: AsyncSession = Depends(get_data_session),
    _: User = Depends(require_admin_or_manager),
):
    """Просмотр расписания другого преподавателя (для управляющего/админа)."""
    result = await db.execute(
        select(Schedule)
        .where(Schedule.user_id == user_id)
        .order_by(Schedule.day_of_week, Schedule.start_time)
    )
    return [_schedule_to_out(s) for s in result.scalars().all()]


@router.post("/", response_model=ScheduleOut, status_code=status.HTTP_201_CREATED)
async def create_schedule(
    body: ScheduleCreate,
    db: AsyncSession = Depends(get_data_session),
    current_user: User = Depends(get_current_user),
):
    user_id = body.user_id or current_user.id

    # Проверка прав: teacher может добавлять только себе
    if current_user.role == "teacher" and user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Вы можете добавлять расписание только себе")

    schedule = Schedule(
        user_id=user_id,
        title=body.title,
        day_of_week=body.day_of_week,
        start_time=_parse_time(body.start_time),
        end_time=_parse_time(body.end_time),
        group_name=body.group_name,
        room=body.room,
        type=body.type,
        source=body.source,
        created_by=current_user.id,
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
    """Массовое добавление записей расписания (после AI-парсинга).

    Дубли (та же пара у того же преподавателя) пропускаются.
    """
    target_user_id = body.user_id or current_user.id
    if current_user.role == "teacher" and target_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Вы можете добавлять расписание только себе")

    from app.services.schedule_dedup import DuplicateTracker
    tracker = DuplicateTracker()
    await tracker.prime(db, target_user_id)

    created = []
    for item in body.items:
        candidate = {
            "title": item.title,
            "day_of_week": item.day_of_week,
            "start_time": item.start_time,
            "end_time": item.end_time,
            "group_name": item.group_name,
        }
        if tracker.is_duplicate(target_user_id, candidate):
            continue

        schedule = Schedule(
            user_id=target_user_id,
            title=item.title,
            day_of_week=item.day_of_week,
            start_time=_parse_time(item.start_time),
            end_time=_parse_time(item.end_time),
            group_name=item.group_name,
            room=item.room,
            type=item.type,
            source=ScheduleSource.PDF_IMPORT,
            created_by=current_user.id,
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
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Запись расписания не найдена")

    # Проверка прав
    if current_user.role == "teacher" and schedule.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Вы можете редактировать только своё расписание")

    update_data = body.model_dump(exclude_unset=True)
    if "start_time" in update_data and update_data["start_time"]:
        update_data["start_time"] = _parse_time(update_data["start_time"])
    if "end_time" in update_data and update_data["end_time"]:
        update_data["end_time"] = _parse_time(update_data["end_time"])

    for key, value in update_data.items():
        if value is not None:
            setattr(schedule, key, value)

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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Запись расписания не найдена")

    if current_user.role == "teacher":
        if schedule.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Вы можете удалять только своё расписание")
        if schedule.source == ScheduleSource.MANAGER:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нельзя удалить запись, добавленную управляющим")

    await db.delete(schedule)
    await db.commit()