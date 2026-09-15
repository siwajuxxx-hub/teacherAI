"""Создание тестового преподавателя Гаврилова."""
import httpx

BASE = "http://localhost:8000"

r = httpx.post(f"{BASE}/api/auth/login", json={"username": "admin", "password": "admin"})
token = r.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Проверяем, есть ли уже
users = httpx.get(f"{BASE}/api/users/", headers=headers).json()
existing = [u for u in users if u["username"] == "gavrilov"]
if existing:
    print(f"ℹ️  Пользователь gavrilov уже существует (id={existing[0]['id']})")
else:
    payload = {
        "username": "gavrilov",
        "password": "gavrilov",
        "full_name": "Гаврилов А.И.",
        "position": "Преподаватель информатики",
        "role": "teacher",
    }
    resp = httpx.post(f"{BASE}/api/users/", headers=headers, json=payload)
    if resp.status_code in (200, 201):
        print(f"✅ Создан пользователь: gavrilov / gavrilov ({resp.json()['full_name']})")
    else:
        print(f"❌ Ошибка: {resp.status_code} — {resp.text}")
