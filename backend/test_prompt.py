"""Проверка: системный промпт содержит сегодняшнюю дату."""
import asyncio
from app.services.ai_service import build_system_context
from app.database import init_databases

async def main():
    await init_databases()
    ctx = await build_system_context("cc9fadf3-0ca6-48af-86c4-912813f27fca")
    print("Первые 800 символов промпта:")
    print(ctx[:800])
    print()
    if "Сегодня:" in ctx and "СЕГОДНЯ" in ctx:
        print("✅ Промпт содержит сегодняшнюю дату и метки СЕГОДНЯ")
    else:
        print("❌ Промпт НЕ содержит дату!")

asyncio.run(main())