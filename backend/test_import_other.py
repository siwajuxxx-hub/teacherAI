"""Тест: учитель просит добавить пары другого преподавателя."""
import httpx

BASE = "http://localhost:8000"

# Логинимся как teacher (Мария Ивановна)
r = httpx.post(f"{BASE}/api/auth/login", json={"username": "teacher", "password": "teacher"})
token = r.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Готовим тестовый файл
test_text = """Вторник
3 пара 12.00-13.30
лк Операционные системы ст.пр. Гаврилов А.И. А 1
лк Базы данных ст.пр. Андреев М.А. Б 204

Среда
5 пара 15.45-17.15
лб Операционные системы ст.пр. Гаврилов А.И. Б 209"""

import tempfile, os
with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
    f.write(test_text)
    tmp = f.name

try:
    with open(tmp, "rb") as f:
        result = httpx.post(
            f"{BASE}/api/chat/upload",
            headers=headers,
            files={"file": ("schedule.txt", f, "text/plain")},
            data={"message": "добавь пары Гаврилова А.И."},
            timeout=120,
        ).json()

    print(f"Статус: {result['status']}")
    print(f"Преподаватель: {result.get('teacher', 'N/A')}")
    print(f"Записей: {len(result.get('items', []))}")
    for item in result["items"]:
        print(f"  - {item['title']} | день={item['day_of_week']} | {item['start_time']}-{item['end_time']} | гр. {item['group_name']}")

    if len(result["items"]) > 0:
        print("\n✅ УСПЕХ: пары Гаврилова найдены для Марии Ивановны!")
    else:
        print("\n⚠️  Предупреждение: записей 0 — возможно AI не понял запрос или ФИО")

    # Проверяем что в истории чата у teacher два сообщения
    print()
    h = httpx.get(f"{BASE}/api/chat/history", headers=headers, params={"limit": 4}).json()
    for msg in h:
        print(f"[{msg['role']}] {msg['content'][:100]}")

finally:
    os.unlink(tmp)