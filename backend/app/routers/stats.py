"""Статистика и обзор по преподавателям (для управляющего и администратора)."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import date, datetime, timedelta
from typing import Optional

from app.database import get_data_session, AuthSessionLocal
from app.models.data_models import Schedule, Task, TaskStatus
from app.models.auth_models import User, UserRole
from app.security import require_admin_or_manager

router = APIRouter(prefix="/api/stats", tags=["Статистика"])


# ─── Вспомогательные расчёты ─────────────────────────────────────

def _minutes_between(start, end) -> int:
    """Длительность пары в минутах."""
    s = start.hour * 60 + start.minute
    e = end.hour * 60 + end.minute
    return max(0, e - s)


def _count_weekday_in_month(year: int, month: int, weekday: int) -> int:
    """Сколько раз день недели (0=Пн) встречается в месяце."""
    first = date(year, month, 1)
    if month == 12:
        last = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    # ISO weekday: Пн=1 … Вс=7
    target = weekday + 1  # наш формат 0=Пн → ISO 1=Пн
    count = 0
    d = first
    while d <= last:
        if d.isoweekday() == target:
            count += 1
        d += timedelta(days=1)
    return count


def _count_weekday_in_range(start_d: date, end_d: date, weekday: int) -> int:
    """Сколько раз день недели встречается в произвольном диапазоне дат."""
    target = weekday + 1
    count = 0
    d = start_d
    while d <= end_d:
        if d.isoweekday() == target:
            count += 1
        d += timedelta(days=1)
    return count


async def _load_teachers() -> list[dict]:
    """Все активные преподаватели из auth.db."""
    async with AuthSessionLocal() as auth_db:
        result = await auth_db.execute(
            select(User)
            .where(User.is_active == True)
            .order_by(User.full_name)
        )
        users = list(result.scalars().all())

    return [
        {
            "id": u.id,
            "username": u.username,
            "full_name": u.full_name,
            "position": u.position,
            "role": u.role.value if hasattr(u.role, "value") else str(u.role),
        }
        for u in users
    ]


def _task_is_in_month(t: Task, year: int, month: int) -> bool:
    """Попадает ли задача в указанный месяц."""
    if t.due_date:
        return t.due_date.year == year and t.due_date.month == month
    if t.due_month:
        return t.due_month == f"{year:04d}-{month:02d}"
    if t.due_year:
        return t.due_year == year
    # Задача без срока — считаем по дате создания
    return t.created_at is not None and t.created_at.year == year and t.created_at.month == month


# ─── Краткая статистика по одному преподавателю ──────────────────

async def _teacher_stats(db: AsyncSession, teacher_id: str, year: int, month: int) -> dict:
    """Считает показатели преподавателя за месяц."""
    # ── Пары ──
    sched_res = await db.execute(
        select(Schedule).where(Schedule.user_id == teacher_id)
    )
    schedule = list(sched_res.scalars().all())

    lessons_per_month = 0
    total_minutes = 0
    subjects: set[str] = set()
    groups: set[str] = set()

    for s in schedule:
        occurrences = _count_weekday_in_month(year, month, s.day_of_week)
        lessons_per_month += occurrences
        total_minutes += _minutes_between(s.start_time, s.end_time) * occurrences
        if s.title:
            subjects.add(s.title)
        if s.group_name:
            groups.add(s.group_name)

    # ── Задачи ──
    task_res = await db.execute(
        select(Task).where(Task.user_id == teacher_id)
    )
    all_tasks = list(task_res.scalars().all())
    month_tasks = [t for t in all_tasks if _task_is_in_month(t, year, month)]

    done_month = [t for t in month_tasks if t.status == TaskStatus.DONE]
    overdue_month = [
        t for t in month_tasks
        if t.status != TaskStatus.DONE
        and t.due_date is not None
        and t.due_date < date.today()
    ]

    # Завершённые именно в этом месяце (по completed_at)
    completed_this_month = [
        t for t in all_tasks
        if t.status == TaskStatus.DONE
        and t.completed_at is not None
        and t.completed_at.year == year
        and t.completed_at.month == month
    ]

    return {
        "teacher_id": teacher_id,
        "year": year,
        "month": month,
        # пары
        "lessons_per_month": lessons_per_month,
        "lessons_per_week": len(schedule),
        "hours_per_month": round(total_minutes / 60, 1),
        "subjects_count": len(subjects),
        "groups_count": len(groups),
        # задачи
        "tasks_total": len(month_tasks),
        "tasks_done": len(done_month),
        "tasks_completed_in_month": len(completed_this_month),
        "tasks_overdue": len(overdue_month),
        "tasks_pending": len([t for t in month_tasks if t.status == TaskStatus.PENDING]),
        "tasks_in_progress": len([t for t in month_tasks if t.status == TaskStatus.IN_PROGRESS]),
        "completion_rate": (
            round(len(done_month) / len(month_tasks) * 100) if month_tasks else 0
        ),
    }


@router.get("/overview")
async def overview(
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None, ge=1, le=12),
    db: AsyncSession = Depends(get_data_session),
    _: User = Depends(require_admin_or_manager),
):
    """Краткая статистика по всем преподавателям за месяц."""
    today = date.today()
    y = year or today.year
    m = month or today.month

    teachers = await _load_teachers()
    rows = []
    for t in teachers:
        st = await _teacher_stats(db, t["id"], y, m)
        rows.append({
            "id": t["id"],
            "full_name": t["full_name"],
            "username": t["username"],
            "position": t["position"],
            "role": t["role"],
            "has_schedule": st["lessons_per_week"] > 0,
            **st,
        })

    # Итоги по всем
    totals = {
        "teachers_total": len(rows),
        "teachers_with_schedule": len([r for r in rows if r["has_schedule"]]),
        "lessons_per_month": sum(r["lessons_per_month"] for r in rows),
        "hours_per_month": round(sum(r["hours_per_month"] for r in rows), 1),
        "tasks_total": sum(r["tasks_total"] for r in rows),
        "tasks_done": sum(r["tasks_done"] for r in rows),
        "tasks_overdue": sum(r["tasks_overdue"] for r in rows),
    }
    if totals["tasks_total"]:
        totals["completion_rate"] = round(totals["tasks_done"] / totals["tasks_total"] * 100)
    else:
        totals["completion_rate"] = 0

    return {
        "year": y,
        "month": m,
        "totals": totals,
        "teachers": rows,
    }


@router.get("/teacher/{teacher_id}")
async def teacher_detail(
    teacher_id: str,
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None, ge=1, le=12),
    db: AsyncSession = Depends(get_data_session),
    _: User = Depends(require_admin_or_manager),
):
    """Подробная статистика по одному преподавателю за месяц."""
    today = date.today()
    y = year or today.year
    m = month or today.month

    async with AuthSessionLocal() as auth_db:
        res = await auth_db.execute(select(User).where(User.id == teacher_id))
        teacher = res.scalar_one_or_none()

    stats = await _teacher_stats(db, teacher_id, y, m)

    return {
        "teacher": {
            "id": teacher_id,
            "full_name": teacher.full_name if teacher else "—",
            "username": teacher.username if teacher else "—",
            "position": teacher.position if teacher else "—",
        } if teacher else None,
        **stats,
    }


@router.get("/teacher/{teacher_id}/monthly")
async def teacher_monthly(
    teacher_id: str,
    year: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_data_session),
    _: User = Depends(require_admin_or_manager),
):
    """Разбивка показателей по месяцам года — для графиков."""
    y = year or date.today().year
    result = []
    for m in range(1, 13):
        st = await _teacher_stats(db, teacher_id, y, m)
        result.append({
            "month": m,
            "lessons": st["lessons_per_month"],
            "hours": st["hours_per_month"],
            "tasks_total": st["tasks_total"],
            "tasks_done": st["tasks_done"],
        })
    return {"year": y, "teacher_id": teacher_id, "months": result}


@router.get("/all-load")
async def all_load(
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None, ge=1, le=12),
    db: AsyncSession = Depends(get_data_session),
    _: User = Depends(require_admin_or_manager),
):
    """Нагрузка всех преподавателей — сводная таблица."""
    today = date.today()
    y = year or today.year
    m = month or today.month

    teachers = await _load_teachers()
    result = []
    for t in teachers:
        st = await _teacher_stats(db, t["id"], y, m)
        result.append({
            "teacher_id": t["id"],
            "full_name": t["full_name"],
            "lessons": st["lessons_per_month"],
            "hours": st["hours_per_month"],
        })
    return {"year": y, "month": m, "teachers": result}


# ─── Календарь по преподавателям ─────────────────────────────────

@router.get("/calendar")
async def manager_calendar(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    teacher_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_data_session),
    _: User = Depends(require_admin_or_manager),
):
    """Календарь на месяц: пары и задачи преподавателей по конкретным дням.

    Пары (шаблон по дням недели) разворачиваются в реальные даты месяца,
    чтобы управляющий видел, у кого что стоит в каждый день.
    """
    teachers = await _load_teachers()
    if teacher_id:
        teachers = [t for t in teachers if t["id"] == teacher_id]

    teacher_map = {t["id"]: t for t in teachers}

    # ── Расписание выбранных преподавателей ──
    q = select(Schedule)
    if teacher_id:
        q = q.where(Schedule.user_id == teacher_id)
    sched_res = await db.execute(q)
    schedule = list(sched_res.scalars().all())

    # ── Задачи ──
    tq = select(Task)
    if teacher_id:
        tq = tq.where(Task.user_id == teacher_id)
    task_res = await db.execute(tq)
    tasks = list(task_res.scalars().all())

    month_str = f"{year:04d}-{month:02d}"
    first = date(year, month, 1)
    if month == 12:
        last = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)

    # Группируем по ISO-дате
    days: dict[str, dict] = {}

    def day_entry(iso: str) -> dict:
        if iso not in days:
            days[iso] = {"date": iso, "lessons": [], "tasks": []}
        return days[iso]

    # Пары: разворачиваем шаблон недели в даты месяца
    for s in schedule:
        tinfo = teacher_map.get(s.user_id)
        if not tinfo and not teacher_id:
            continue
        d = first
        while d <= last:
            if d.isoweekday() == s.day_of_week + 1:
                day_entry(d.isoformat())["lessons"].append({
                    "id": s.id,
                    "teacher_id": s.user_id,
                    "teacher_name": tinfo["full_name"] if tinfo else "—",
                    "title": s.title,
                    "start_time": s.start_time.strftime("%H:%M"),
                    "end_time": s.end_time.strftime("%H:%M"),
                    "group_name": s.group_name,
                    "room": s.room,
                    "type": s.type.value if hasattr(s.type, "value") else str(s.type),
                })
            d += timedelta(days=1)

    # Задачи: по дате; месячные — в каждый день месяца; годовые — в каждый день года
    for t in tasks:
        tinfo = teacher_map.get(t.user_id)
        if not tinfo and not teacher_id:
            continue
        tname = tinfo["full_name"] if tinfo else "—"
        status = t.status.value if hasattr(t.status, "value") else str(t.status)

        base = {
            "id": t.id,
            "teacher_id": t.user_id,
            "teacher_name": tname,
            "title": t.title,
            "status": status,
            "scope": t.scope.value if hasattr(t.scope, "value") else "none",
            "due_date": t.due_date.isoformat() if t.due_date else None,
            "due_month": t.due_month,
            "due_year": t.due_year,
        }

        if t.due_date and t.due_date.year == year and t.due_date.month == month:
            day_entry(t.due_date.isoformat())["tasks"].append(base)
        elif t.scope and t.scope.value == "month" and t.due_month == month_str:
            d = first
            while d <= last:
                day_entry(d.isoformat())["tasks"].append(base)
                d += timedelta(days=1)
        elif t.scope and t.scope.value == "year" and t.due_year == year:
            d = first
            while d <= last:
                day_entry(d.isoformat())["tasks"].append(base)
                d += timedelta(days=1)

    # Сортируем пары по времени внутри дня
    for entry in days.values():
        entry["lessons"].sort(key=lambda x: x["start_time"])

    return {
        "year": year,
        "month": month,
        "teachers": [
            {"id": t["id"], "full_name": t["full_name"], "position": t["position"]}
            for t in teachers
        ],
        "days": [days[k] for k in sorted(days.keys())],
    }