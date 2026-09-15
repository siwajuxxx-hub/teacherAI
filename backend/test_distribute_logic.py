"""Проверка логики распределения БЕЗ AI — подставляем результат парсера.

Доказывает: пары заносятся только тем, у кого есть учётная запись,
и повторные пары не дублируются.
"""
import asyncio
from unittest.mock import patch
from app.database import init_databases, DataSessionLocal, AuthSessionLocal
from app.models.auth_models import User
from app.models.data_models import Schedule
from app.services.teacher_matcher import find_user_by_teacher_name, clean_teacher_name
from app.services.schedule_dedup import DuplicateTracker
from sqlalchemy import select, delete

# «Результат AI»: 6 пар у 4 преподавателей.
# Учётные записи есть только у Болохов И.В. и Шапуленкова Е.К.
FAKE_PARSED = {"items": [
    {"title": "Математика", "day_of_week": 0, "start_time": "09:00", "end_time": "10:30",
     "group_name": "А-1", "room": "101", "teacher": "Болохов И.В."},
    {"title": "Физика", "day_of_week": 1, "start_time": "10:45", "end_time": "12:15",
     "group_name": "А-2", "room": "102", "teacher": "ст.пр. Болохов И.В."},
    {"title": "Информатика", "day_of_week": 2, "start_time": "09:00", "end_time": "10:30",
     "group_name": "Б-1", "room": "203", "teacher": "Шапуленкова Е.К."},
    {"title": "Схемотехника", "day_of_week": 3, "start_time": "12:30", "end_time": "14:00",
     "group_name": "Б-2", "room": "305", "teacher": "и.о. доцента Шапуленкова Е.К."},
    # Несуществующие учётки — пары НЕ должны добавиться
    {"title": "Химия", "day_of_week": 4, "start_time": "09:00", "end_time": "10:30",
     "group_name": "В-1", "room": "401", "teacher": "Певцова Л.С."},
    {"title": "История", "day_of_week": 5, "start_time": "10:45", "end_time": "12:15",
     "group_name": "В-2", "room": "402", "teacher": "Неизвестный Н.Н."},
]}


async def distribute(db, items, created_by):
    """Точная копия логики распределения из /api/chat/upload."""
    by_teacher: dict[str, list[dict]] = {}
    for item in items:
        tname = clean_teacher_name(item.get("teacher", ""))
        if not tname:
            continue
        by_teacher.setdefault(tname.lower(), []).append(item)

    tracker = DuplicateTracker()
    added_total, skipped_total = 0, 0
    found, not_found = [], []

    for tname, t_items in by_teacher.items():
        user = await find_user_by_teacher_name(db, tname)
        if not user:
            not_found.append(tname)
            continue
        found.append(user.full_name)
        await tracker.prime(db, user.id)

        for item in t_items:
            if tracker.is_duplicate(user.id, item):
                skipped_total += 1
                continue
            from datetime import time as _t
            def pt(s):
                h, m = s.split(":"); return _t(int(h), int(m))
            db.add(Schedule(
                user_id=user.id, title=item["title"], day_of_week=item["day_of_week"],
                start_time=pt(item["start_time"]), end_time=pt(item["end_time"]),
                group_name=item.get("group_name", ""), room=item.get("room", ""),
                source="pdf_import", created_by=created_by,
            ))
            added_total += 1

    await db.commit()
    return found, not_found, added_total, skipped_total


async def main():
    from app.models.data_models import ScheduleSource, ScheduleType
    await init_databases()

    async with AuthSessionLocal() as s:
        users = (await s.execute(select(User))).scalars().all()
        by_name = {u.full_name: u for u in users}
    admin = by_name.get("Администратор") or users[0]

    print("=== Учётные записи в системе ===")
    for u in users:
        print(f"  {u.full_name:28} {u.role.value}")

    # Чистим расписание у всех
    print("\n=== Уборка расписания ===")
    async with DataSessionLocal() as db:
        for u in users:
            n = len((await db.execute(select(Schedule).where(Schedule.user_id == u.id))).scalars().all())
            if n:
                await db.execute(delete(Schedule).where(Schedule.user_id == u.id))
                print(f"  {u.full_name}: удалено {n}")
        await db.commit()

    print("\n=== Распределение (6 пар от 4 преподавателей) ===")
    async with DataSessionLocal() as db:
        found, not_found, added, skipped = await distribute(db, FAKE_PARSED["items"], admin.id)

    print(f"\n  Найдены учётные записи ({len(found)}): {found}")
    print(f"  Нет учётной записи ({len(not_found)}): {not_found}")
    print(f"  Добавлено пар: {added} (ожидается 4)")
    print(f"  Пропущено: {skipped}")

    assert added == 4, f"ожидалось 4 пары, добавлено {added}"
    assert len(found) == 2, f"ожидалось 2 преподавателя, найдено {len(found)}"

    print("\n=== Что в календарях ===")
    async with DataSessionLocal() as db:
        for u in users:
            rows = (await db.execute(select(Schedule).where(Schedule.user_id == u.id))).scalars().all()
            if rows:
                print(f"\n  {u.full_name}: {len(rows)} пар")
                for r in rows:
                    d = ['Пн','Вт','Ср','Чт','Пт','Сб','Вс'][r.day_of_week]
                    print(f"    {d} {r.start_time:%H:%M}-{r.end_time:%H:%M} {r.title:16} гр.{r.group_name} ауд.{r.room}")

        # Пар у несуществующих не должно быть
        for name in ["Певцова Л.С.", "Неизвестный Н.Н."]:
            u = by_name.get(name)
            if u:
                rows = (await db.execute(select(Schedule).where(Schedule.user_id == u.id))).scalars().all()
                assert not rows, f"{name} получил пары без учётки!"
    print("\n  ✅ Пары получили ТОЛЬКО преподаватели с учётными записями")

    print("\n=== Повторное распределение (антидубли) ===")
    async with DataSessionLocal() as db:
        found2, nf2, added2, skipped2 = await distribute(db, FAKE_PARSED["items"], admin.id)
    print(f"  Добавлено: {added2} (ожидается 0)")
    print(f"  Пропущено как дубли: {skipped2} (ожидается 4)")
    assert added2 == 0, f"появились дубли: {added2}"
    assert skipped2 == 4, f"должно быть пропущено 4, а пропущено {skipped2}"
    print("  ✅ Дубли НЕ добавлены")

    print("\n=== Итог ===")
    async with DataSessionLocal() as db:
        total = len((await db.execute(select(Schedule))).scalars().all())
    print(f"  Всего пар в системе: {total} (ожидается 4)")

    # Уборка
    async with DataSessionLocal() as db:
        await db.execute(delete(Schedule))
        await db.commit()
    print("  тестовые данные удалены")

    print("\n✅ ВСЕ ПРОВЕРКИ РАСПРЕДЕЛЕНИЯ ПРОЙДЕНЫ")


asyncio.run(main())