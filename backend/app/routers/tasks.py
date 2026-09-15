from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import date, datetime
from typing import Optional

from app.database import get_data_session
from app.models.data_models import Task, TaskStatus, TaskScope
from app.models.auth_models import User
from app.schemas.data_schemas import (
    TaskCreate, TaskUpdate, TaskStatusUpdate, TaskOut,
)
from app.security import get_current_user, require_admin_or_manager

router = APIRouter(prefix="/api/tasks", tags=["Задачи"])


# ─── Разбор и проверка полей ─────────────────────────────────────

def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Неверный формат даты: {s}. Ожидается YYYY-MM-DD",
        )


def _parse_month(s: str | None) -> str | None:
    """Проверяет формат YYYY-MM."""
    if not s:
        return None
    try:
        datetime.strptime(s, "%Y-%m")
        return s
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Неверный формат месяца: {s}. Ожидается YYYY-MM",
        )


def _parse_year(y: int | None) -> int | None:
    if y is None:
        return None
    if not (2000 <= int(y) <= 2100):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Неверный год: {y}. Ожидается 2000–2100",
        )
    return int(y)


def _normalize_scope(
    scope: TaskScope | None,
    due_date: date | None,
    due_month: str | None,
    due_year: int | None,
) -> TaskScope:
    """Определяет корректный период задачи по заполненным полям."""
    if scope == TaskScope.DAY and due_date:
        return TaskScope.DAY
    if scope == TaskScope.MONTH and due_month:
        return TaskScope.MONTH
    if scope == TaskScope.YEAR and due_year:
        return TaskScope.YEAR
    # Период не задан явно — выводим из заполненных полей
    if due_date:
        return TaskScope.DAY
    if due_month:
        return TaskScope.MONTH
    if due_year:
        return TaskScope.YEAR
    return TaskScope.NONE


def _eff_due(t: Task) -> Optional[date]:
    """Последний день срока задачи (для проверки просрочки и сортировки)."""
    if t.due_date:
        return t.due_date
    if t.due_month:
        try:
            y, m = int(t.due_month[:4]), int(t.due_month[5:7])
            # последний день месяца
            if m == 12:
                return date(y, 12, 31)
            return date(y, m + 1, 1).fromordinal(date(y, m + 1, 1).toordinal() - 1)
        except Exception:
            return None
    if t.due_year:
        try:
            return date(int(t.due_year), 12, 31)
        except Exception:
            return None
    return None


def _is_overdue(t: Task) -> bool:
    if t.status == TaskStatus.DONE:
        return False
    eff = _eff_due(t)
    return bool(eff and eff < date.today())


def _task_to_out(t: Task) -> TaskOut:
    status_value = TaskStatus.OVERDUE if _is_overdue(t) else t.status
    return TaskOut(
        id=t.id,
        user_id=t.user_id,
        title=t.title,
        description=t.description,
        status=status_value,
        scope=t.scope or TaskScope.NONE,
        due_date=t.due_date.isoformat() if t.due_date else None,
        due_month=t.due_month,
        due_year=t.due_year,
        completed_at=t.completed_at,
        assigned_by=t.assigned_by,
        created_at=t.created_at,
    )


# ─── Чтение ──────────────────────────────────────────────────────

@router.get("/my", response_model=list[TaskOut])
async def get_my_tasks(
    db: AsyncSession = Depends(get_data_session),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Task).where(Task.user_id == current_user.id).order_by(Task.created_at.desc())
    )
    tasks = [_task_to_out(t) for t in result.scalars().all()]
    # Сортировка: сначала незавершённые по сроку, затем выполненные по дате завершения
    tasks.sort(key=lambda t: (
        t.status == TaskStatus.DONE,
        t.due_date or t.due_month or (str(t.due_year) if t.due_year else "9999"),
    ))
    return tasks


@router.get("/user/{user_id}", response_model=list[TaskOut])
async def get_user_tasks(
    user_id: str,
    db: AsyncSession = Depends(get_data_session),
    _: User = Depends(require_admin_or_manager),
):
    result = await db.execute(
        select(Task).where(Task.user_id == user_id).order_by(Task.created_at.desc())
    )
    return [_task_to_out(t) for t in result.scalars().all()]


# ─── Изменение ───────────────────────────────────────────────────

@router.post("/", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(
    body: TaskCreate,
    db: AsyncSession = Depends(get_data_session),
    current_user: User = Depends(get_current_user),
):
    user_id = body.user_id or current_user.id

    # teacher может создавать задачи только себе
    if current_user.role == "teacher" and user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Вы можете создавать задачи только себе")

    due_date = _parse_date(body.due_date)
    due_month = _parse_month(body.due_month)
    due_year = _parse_year(body.due_year)
    scope = _normalize_scope(body.scope, due_date, due_month, due_year)

    task = Task(
        user_id=user_id,
        title=body.title,
        description=body.description,
        status=body.status,
        scope=scope,
        due_date=due_date if scope == TaskScope.DAY else None,
        due_month=due_month if scope == TaskScope.MONTH else None,
        due_year=due_year if scope == TaskScope.YEAR else None,
        completed_at=datetime.utcnow() if body.status == TaskStatus.DONE else None,
        assigned_by=current_user.id if user_id != current_user.id else None,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return _task_to_out(task)


@router.put("/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: str,
    body: TaskUpdate,
    db: AsyncSession = Depends(get_data_session),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена")

    if current_user.role == "teacher" and task.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Вы можете редактировать только свои задачи")

    data = body.model_dump(exclude_unset=True)

    if "due_date" in data:
        data["due_date"] = _parse_date(data["due_date"])
    if "due_month" in data:
        data["due_month"] = _parse_month(data["due_month"])
    if "due_year" in data:
        data["due_year"] = _parse_year(data["due_year"])

    for key in ("title", "description"):
        if data.get(key) is not None:
            setattr(task, key, data[key])

    # Период: применяем согласованно
    wants_scope = data.get("scope")
    touched_dates = any(k in data for k in ("due_date", "due_month", "due_year"))

    if touched_dates or wants_scope is not None:
        due_date = data.get("due_date", task.due_date)
        due_month = data.get("due_month", task.due_month)
        due_year = data.get("due_year", task.due_year)

        scope = _normalize_scope(wants_scope, due_date, due_month, due_year)

        task.scope = scope
        task.due_date = due_date if scope == TaskScope.DAY else None
        task.due_month = due_month if scope == TaskScope.MONTH else None
        task.due_year = due_year if scope == TaskScope.YEAR else None

    await db.commit()
    await db.refresh(task)
    return _task_to_out(task)


@router.patch("/{task_id}/status", response_model=TaskOut)
async def update_task_status(
    task_id: str,
    body: TaskStatusUpdate,
    db: AsyncSession = Depends(get_data_session),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена")

    if current_user.role == "teacher" and task.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Вы можете менять только свои задачи")

    task.status = body.status
    # Фиксируем дату завершения
    if body.status == TaskStatus.DONE:
        task.completed_at = task.completed_at or datetime.utcnow()
    else:
        task.completed_at = None

    await db.commit()
    await db.refresh(task)
    return _task_to_out(task)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: str,
    db: AsyncSession = Depends(get_data_session),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена")

    if current_user.role == "teacher" and task.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Вы можете удалять только свои задачи")

    await db.delete(task)
    await db.commit()
