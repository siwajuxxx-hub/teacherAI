"""Отладка teacher_matcher."""
import asyncio, json
from app.services.teacher_matcher import (
    find_user_by_teacher_name, clean_teacher_name, extract_surname, names_match,
)
from app.database import AuthSessionLocal

async def main():
    async with AuthSessionLocal() as db:
        from app.models.auth_models import User
        from sqlalchemy import select
        result = await db.execute(select(User))
        users = list(result.scalars().all())
        print("=== Все пользователи ===")
        for u in users:
            print(f"  {u.username}: {u.full_name} ({u.role.value})")

        print("\n=== Тест сопоставления имён ===")
        for test_name in [
            "Гаврилов А.И.",
            "Гаврилова А.И.",
            "ст.пр. Гаврилов А.И.",
            "Певцова Л.С.",
            "Андреев М.А.",
            "Кабанова И.А.",
        ]:
            cleaned = clean_teacher_name(test_name)
            found = await find_user_by_teacher_name(db, cleaned)
            print(f"  '{test_name}' -> cleaned='{cleaned}' -> user={found.username if found else 'NOT FOUND'}")

asyncio.run(main())