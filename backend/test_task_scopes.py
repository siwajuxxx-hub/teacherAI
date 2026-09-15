"""Проверка миграции tasks: новые колонки, определение scope, просрочка."""
import asyncio
from datetime import date, datetime, timedelta
from sqlalchemy import select, text
from app.database import init_databases, DataSessionLocal
from app.models.data_models import Task, TaskScope, TaskStatus


async def main():
    await init_databases()
    print("Миграция выполнена")

    async with DataSessionLocal() as db:
        r = await db.execute(text("PRAGMA table_info(tasks)"))
        cols = [row[1] for row in r.fetchall()]
        print("Колонки tasks:", ", ".join(cols))
        for need in ("scope", "due_month", "due_year", "completed_at"):
            assert need in cols, f"Нет колонки {need}"
        print("OK: все новые колонки на месте")

        # Проверяем миграцию старых записей
        r = await db.execute(text("SELECT COUNT(*) FROM tasks WHERE status='done' AND completed_at IS NULL"))
        n = r.scalar()
        print(f"Выполненных без completed_at: {n} (ожидается 0)")
        assert n == 0

        # Задачи с due_date должны получить scope='day'
        r = await db.execute(text("SELECT COUNT(*) FROM tasks WHERE due_date IS NOT NULL AND (scope IS NULL OR scope='none')"))
        n2 = r.scalar()
        print(f"С датой, но без scope='day': {n2} (ожидается 0)")
        assert n2 == 0

    # Проверяем логику просрочки и периодов
    from app.routers.tasks import _eff_due, _is_overdue, _normalize_scope

    today = date.today()

    # Месячная задача: срок = конец месяца
    t_month = Task(user_id="x", title="Месячная", scope=TaskScope.MONTH, due_month="2026-02", status=TaskStatus.PENDING)
    print(f"\nМесяц 2026-02 -> срок {_eff_due(t_month)}")
    assert _eff_due(t_month) == date(2026, 2, 28), _eff_due(t_month)

    t_month12 = Task(user_id="x", title="Декабрь", scope=TaskScope.MONTH, due_month="2026-12", status=TaskStatus.PENDING)
    assert _eff_due(t_month12) == date(2026, 12, 31), _eff_due(t_month12)
    print(f"Месяц 2026-12 -> срок {_eff_due(t_month12)}")

    t_year = Task(user_id="x", title="Годовая", scope=TaskScope.YEAR, due_year=2026, status=TaskStatus.PENDING)
    assert _eff_due(t_year) == date(2026, 12, 31)
    print(f"Год 2026 -> срок {_eff_due(t_year)}")

    # Просрочка
    past = Task(user_id="x", title="Прошлая", scope=TaskScope.DAY, due_date=today - timedelta(days=1), status=TaskStatus.PENDING)
    future = Task(user_id="x", title="Будущая", scope=TaskScope.DAY, due_date=today + timedelta(days=5), status=TaskStatus.PENDING)
    done_past = Task(user_id="x", title="Готово", scope=TaskScope.DAY, due_date=today - timedelta(days=3), status=TaskStatus.DONE)
    print(f"\nПрошлая просрочена? {_is_overdue(past)} (ожидается True)")
    print(f"Будущая просрочена?  {_is_overdue(future)} (ожидается False)")
    print(f"Готовая просрочена?  {_is_overdue(done_past)} (ожидается False)")
    assert _is_overdue(past) and not _is_overdue(future) and not _is_overdue(done_past)

    # Определение scope
    assert _normalize_scope(None, today, None, None) == TaskScope.DAY
    assert _normalize_scope(None, None, "2026-09", None) == TaskScope.MONTH
    assert _normalize_scope(None, None, None, 2026) == TaskScope.YEAR
    assert _normalize_scope(None, None, None, None) == TaskScope.NONE
    print("\nOK: определение периода работает")

    print("\nВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


asyncio.run(main())