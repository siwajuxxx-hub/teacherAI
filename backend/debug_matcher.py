"""Отладка: что возвращает parse_schedule_all."""
import httpx, json, tempfile, os

BASE = "http://localhost:8000"
r = httpx.post(f"{BASE}/api/auth/login", json={"username": "manager", "password": "manager"})
token = r.json()["access_token"]

# Проверим пользователей в системе
print("=== Все преподаватели ===")
users = httpx.get(f"{BASE}/api/users/", headers={"Authorization": f"Bearer {token}"}).json()
for u in users:
    print(f"  {u['username']}: {u['full_name']} ({u['role']})")

# Проверим matcher напрямую
print("\n=== Проверка teacher_matcher ===")
from app.services.teacher_matcher import find_user_by_teacher_name, clean_teacher_name, extract_surname
from app.database import AuthSessionLocal
from app.models.auth_models import User
from sqlalchemy import select
import asyncio

async def check():
    async with AuthSessionLocal() as db:
        for test_name in ["Гаврилов А.И.", "Певцова Л.С.", "Гаврилова А.И.", "ст.пр. Гаврилов А.И."]:
            cleaned = clean_teacher_name(test_name)
            found = await find_user_by_teacher_name(db, cleaned)
            print(f"  '{test_name}' -> cleaned='{cleaned}' -> user={found.username if found else 'NOT FOUND'}")

asyncio.run(check())