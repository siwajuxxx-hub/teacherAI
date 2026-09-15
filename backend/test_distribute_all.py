"""Тест: управляющий распределяет расписание всем преподавателям."""
import httpx, tempfile, os

BASE = "http://localhost:8000"

# Логинимся как manager
r = httpx.post(f"{BASE}/api/auth/login", json={"username": "manager", "password": "manager"})
token = r.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}
me = httpx.get(f"{BASE}/api/auth/me", headers=headers).json()
print(f"Управляющий: {me['full_name']} ({me['role']})")

# Тестовый файл с двумя преподавателями
test_text = """Понедельник
2 пара 10.15-11.45
лк Электроэнергетические системы и сети ст.пр. Певцова Л.С. 518

Вторник
3 пара 12.00-13.30
лк Операционные системы ст.пр. Гаврилов А.И. А 1
лк Базы данных ст.пр. Андреев М.А. Б 204"""

with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
    f.write(test_text)
    tmp = f.name

try:
    # Загружаем с командой «добавь всем преподавателям»
    with open(tmp, "rb") as f:
        result = httpx.post(
            f"{BASE}/api/chat/upload",
            headers=headers,
            files={"file": ("schedule.txt", f, "text/plain")},
            data={"message": "добавь всем преподавателям их пары"},
            timeout=120,
        ).json()

    print(f"\nСтатус: {result['status']}")
    print(f"Сообщение: {result.get('message', 'N/A')}")
    print(f"Преподавателей: {result.get('teachers_found', 0)}")
    print(f"Записей добавлено: {result.get('total_added', 0)}")

    # Проверяем расписание у gavrilov
    print("\n--- Проверка расписания Гаврилова ---")
    r = httpx.post(f"{BASE}/api/auth/login", json={"username": "gavrilov", "password": "gavrilov"})
    gav_token = r.json()["access_token"]
    gav_sched = httpx.get(f"{BASE}/api/schedule/my", headers={"Authorization": f"Bearer {gav_token}"}).json()
    for s in gav_sched:
        print(f"  {s['title']} | день={s['day_of_week']} | {s['start_time']}-{s['end_time']}")

    # Проверяем расписание у teacher (Мария Ивановна — у неё нет пар в этом файле)
    print("\n--- Проверка расписания Марии Ивановны ---")
    r = httpx.post(f"{BASE}/api/auth/login", json={"username": "teacher", "password": "teacher"})
    t_token = r.json()["access_token"]
    t_sched = httpx.get(f"{BASE}/api/schedule/my", headers={"Authorization": f"Bearer {t_token}"}).json()
    for s in t_sched:
        print(f"  {s['title']} | день={s['day_of_week']} | {s['start_time']}-{s['end_time']}")

    if gav_sched:
        print("\n✅ УСПЕХ: пары Гаврилова добавлены в его календарь!")
    else:
        print("\n⚠️  Гаврилов без пар — возможно AI не извлёк поле teacher")

finally:
    os.unlink(tmp)