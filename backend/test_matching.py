"""Проверка сопоставления ФИО из расписания с учётными записями."""
import asyncio
from app.database import init_databases, DataSessionLocal
from app.services.teacher_matcher import find_user_by_teacher_name, clean_teacher_name
from app.services.ai_service import split_schedule_text

# ФИО из реальных учётных записей
ACCOUNTS = ["Шапуленкова Е.К.", "Болохов И.В.", "Мария Ивановна", "Гаврилов А.И."]

# Как их может вернуть AI из расписания (разные варианты написания)
from_schedule = [
    "Шапуленкова Е.К.", "шапуленкова е.к.", "Шапуленкова Екатерина Константиновна",
    "ст.пр. Шапуленкова Е.К.", "Болохов И.В.", "Болохов Илья Витальевич",
    "и.о. доцента Болохов И.В.", "Гаврилов А.И.", "Гаврилов А. И.",
    "Мария Ивановна", "Певцова Л.С.",  # последней нет в системе
]


async def main():
    await init_databases()
    print("=== Чистка ФИО от званий ===")
    for n in ["ст.пр. Шапуленкова Е.К.", "и.о. доцента Болохов И.В.", "доц. Певцова Л.С."]:
        print(f"  «{n}» -> «{clean_teacher_name(n)}»")

    print("\n=== Сопоставление с учётными записями ===")
    async with DataSessionLocal() as db:
        for name in from_schedule:
            u = await find_user_by_teacher_name(db, clean_teacher_name(name))
            mark = "✅" if u else "❌"
            print(f"  {mark} «{name}» -> {u.full_name if u else 'НЕ НАЙДЕН (нет учётной записи)'}")

asyncio.run(main())

print("\n=== Чанкование текста расписания ===")
text = ("Певцова Л.С.\n" + "занятие " * 400 + "\n") * 8
chunks = split_schedule_text(text)
print(f"  Исходный текст: {len(text)} символов")
print(f"  Кусков: {len(chunks)}")
for i, c in enumerate(chunks):
    print(f"    кусок {i+1}: {len(c)} символов")
joined = "".join(chunks)
print(f"  Склеенный обратно: {len(joined)} символов")
print(f"  Ничего не потеряно: {'ДА' if len(joined) == len(text) else 'НЕТ'}")
assert len(joined) == len(text), "чанкование теряет текст!"