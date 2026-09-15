"""Тест проверки дублей и учётных записей при распределении расписания."""
import asyncio
from app.database import init_databases, DataSessionLocal, AuthSessionLocal
from app.models.data_models import Schedule, ScheduleType, ScheduleSource
from app.services.schedule_dedup import DuplicateTracker, dup_key, load_existing_keys
from app.models.auth_models import User
from sqlalchemy import select, delete


async def main():
    await init_databases()

    async with AuthSessionLocal() as s:
        r = await s.execute(select(User).where(User.username == "teacher"))
        teacher = r.scalar_one()

    # Чистим расписание тестового преподавателя
    async with DataSessionLocal() as db:
        await db.execute(delete(Schedule).where(Schedule.user_id == teacher.id))
        await db.commit()

    items = [
        {"title": "Математика", "day_of_week": 0, "start_time": "09:00", "end_time": "10:30", "group_name": "ЭС1-24з"},
        {"title": "Физика",    "day_of_week": 1, "start_time": "10:40", "end_time": "12:10", "group_name": "ЭС1-24з"},
        {"title": "Математика", "day_of_week": 0, "start_time": "09:00", "end_time": "10:30", "group_name": "ЭС1-24з"},  # дубль внутри файла
    ]

    print("=== 1. Первый импорт (3 элемента, один — дубль внутри файла) ===")
    async with DataSessionLocal() as db:
        tracker = DuplicateTracker()
        await tracker.prime(db, teacher.id)
        added = 0
        for it in items:
            if tracker.is_duplicate(teacher.id, it):
                print(f"  ПРОПУЩЕН дубль: {it['title']} {it['start_time']}")
                continue
            db.add(Schedule(
                user_id=teacher.id, title=it["title"], day_of_week=it["day_of_week"],
                start_time=__import__("datetime").time(int(it["start_time"][:2]), int(it["start_time"][3:])),
                end_time=__import__("datetime").time(int(it["end_time"][:2]), int(it["end_time"][3:])),
                group_name=it["group_name"], room="101",
                type=ScheduleType.LESSON, source=ScheduleSource.PDF_IMPORT,
                created_by=teacher.id,
            ))
            added += 1
        await db.commit()
    print(f"  Добавлено: {added}, пропущено: {tracker.skipped}")
    assert added == 2, f"Ожидалось 2, получено {added}"

    print("\n=== 2. Повторный импорт того же файла (всё должно быть пропущено) ===")
    async with DataSessionLocal() as db:
        tracker2 = DuplicateTracker()
        await tracker2.prime(db, teacher.id)
        added2 = 0
        for it in items:
            if tracker2.is_duplicate(teacher.id, it):
                continue
            added2 += 1
    print(f"  Добавлено: {added2}, пропущено: {tracker2.skipped}")
    assert added2 == 0, f"Дублей быть не должно, добавлено {added2}"

    print("\n=== 3. Одинаковая пара у РАЗНЫХ преподавателей — не дубль ===")
    async with AuthSessionLocal() as s:
        r = await s.execute(select(User).where(User.username == "gavrilov"))
        other = r.scalar_one()
    async with DataSessionLocal() as db:
        t3 = DuplicateTracker()
        await t3.prime(db, other.id)
        dup = t3.is_duplicate(other.id, items[0])
    print(f"  Для другого преподавателя дубль? {dup}")
    assert dup is False, "У разных преподавателей одинаковые пары — это НЕ дубль"

    print("\n=== 4. Ключ учитывает аудиторию? Нет — учитывает группу, день, время, название ===")
    k1 = dup_key("Математика", 0, "09:00", "10:30", "ЭС1-24з")
    k2 = dup_key("математика ", 0, "09:00", "10:30", "эс1-24з")
    print(f"  Регистр/пробелы нормализуются: {k1 == k2}")
    assert k1 == k2

    print("\n=== 5. Итоговое расписание ===")
    async with DataSessionLocal() as db:
        keys = await load_existing_keys(db, teacher.id)
        r = await db.execute(select(Schedule).where(Schedule.user_id == teacher.id))
        for s in r.scalars().all():
            print(f"  [{s.day_of_week}] {s.title} {s.start_time.strftime('%H:%M')} гр.{s.group_name}")
        print(f"  Всего ключей: {len(keys)}")
        assert len(keys) == 2

    # Уборка
    async with DataSessionLocal() as db:
        await db.execute(delete(Schedule).where(Schedule.user_id == teacher.id))
        await db.commit()

    print("\nВСЕ ТЕСТЫ ДУБЛЕЙ ПРОЙДЕНЫ")


asyncio.run(main())