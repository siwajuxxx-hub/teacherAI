"""Тест распределения всем — с отладкой."""
import httpx, tempfile, os

BASE = "http://localhost:8000"

# manager логин
r = httpx.post(f"{BASE}/api/auth/login", json={"username": "manager", "password": "manager"})
if r.status_code != 200:
    print(f"LOGIN FAILED: {r.status_code} {r.text}")
    exit(1)
token = r.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Файл
text = """Понедельник\n2 пара 10.15-11.45\nлк Электроэнергетические системы и сети ст.пр. Певцова Л.С. 518\n\nВторник\n3 пара 12.00-13.30\nлк Операционные системы ст.пр. Гаврилов А.И. А 1"""

with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
    f.write(text)
    tmp = f.name

try:
    with open(tmp, "rb") as f:
        resp = httpx.post(
            f"{BASE}/api/chat/upload",
            headers=headers,
            files={"file": ("schedule.txt", f, "text/plain")},
            data={"message": "добавь всем преподавателям их пары"},
            timeout=120,
        )
    print(f"HTTP {resp.status_code}")
    if resp.status_code == 200:
        result = resp.json()
        print(f"Статус: {result.get('status')}")
        print(f"Сообщение: {result.get('message')}")
        print(f"Преподавателей: {result.get('teachers_found')}")
        print(f"Записей: {result.get('total_added')}")
        print(f"Не найдены: {result.get('not_found')}")
    else:
        print(f"Ошибка: {resp.text[:300]}")
finally:
    os.unlink(tmp)