"""Прямой вызов парсера — видим реальное исключение."""
import asyncio, glob, os, traceback
from app.services.file_parser import extract_text_from_file
from app.services.ai_service import create_ai_provider, split_schedule_text
from app.database import init_databases

DOCX = glob.glob(r"C:\Users\siwaj\.dsh\attachments\v1\files\**\*.docx", recursive=True)


async def main():
    await init_databases()
    with open(DOCX[0], "rb") as f:
        text = await extract_text_from_file(f.read(), os.path.basename(DOCX[0]))

    chunks = split_schedule_text(text)
    print(f"Текст: {len(text)} символов, кусков: {len(chunks)}")

    provider = await create_ai_provider()
    print(f"Провайдер: {type(provider).__name__}, модель: {provider.model}")

    try:
        parsed = await provider.parse_schedule_all(text, user_query="добавь всем преподавателям")
        items = parsed.get("items", [])
        print(f"\n✅ Успешно: {len(items)} записей")

        teachers = {}
        for it in items:
            t = (it.get("teacher") or "—").strip()
            teachers.setdefault(t, 0)
            teachers[t] += 1
        print(f"Преподавателей: {len(teachers)}")
        for t, n in sorted(teachers.items()):
            print(f"  {t:32} {n} пар")

        # Проверяем поля на корректность
        bad = [i for i in items if not i.get("title") or i.get("day_of_week") is None]
        print(f"\nЗаписей с пустым title/day: {len(bad)}")

    except Exception as e:
        print(f"\n ИСКЛЮЧЕНИЕ: {type(e).__name__}")
        print(f"   str(): {str(e)!r}")
        print(f"   repr(): {repr(e)[:400]}")
        traceback.print_exc()


asyncio.run(main())