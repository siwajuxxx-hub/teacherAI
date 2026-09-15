"""Что реально возвращает parse_schedule_all для тестового текста."""
import asyncio
from app.services.ai_service import create_ai_provider

TEST_TEXT = """Понедельник
2 пара 10.15-11.45
лк Электроэнергетические системы и сети ст.пр. Певцова Л.С. 518

Вторник
3 пара 12.00-13.30
лк Операционные системы ст.пр. Гаврилов А.И. А 1
лк Базы данных ст.пр. Андреев М.А. Б 204"""

async def main():
    provider = await create_ai_provider()
    result = await provider.parse_schedule_all(TEST_TEXT, user_query="добавь всем преподавателям их пары")
    import json
    print(json.dumps(result, ensure_ascii=False, indent=2))

asyncio.run(main())