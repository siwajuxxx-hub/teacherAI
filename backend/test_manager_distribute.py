"""Сквозной тест: управляющий загружает расписание и распределяет всем."""
import httpx, json, os

BASE = "http://localhost:8000"
DOCX = r"C:\Users\siwaj\.dsh\attachments\v1\files\af\af7b010845e044a9829941ee63419b5fd8e9904c8422498be6dea8427afb38f8\Raspisanie_zanyatiy_3_kursa_bakalavryi_zaochnaya_forma_obucheniya_(ustanovochnaya_sessiya).docx"


def login(u, p):
    r = httpx.post(f"{BASE}/api/auth/login", json={"username": u, "password": p})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


M = login("manager", "manager")

# Кто вообще есть в системе
users = httpx.get(f"{BASE}/api/users/", headers=M, timeout=30).json()
print("=== Учётные записи ===")
teachers_with_acc = []
for u in users:
    role = u.get("role")
    print(f"  {u['username']:12} {u['full_name']:28} роль={role}")
    if role == "teacher":
        teachers_with_acc.append(u["full_name"])

print(f"\nПреподаватели с учётной записью: {teachers_with_acc}")

# Чистим их расписание, чтобы тест был чистым
print("\n=== Уборка расписания преподавателей ===")
for u in users:
    if u.get("role") != "teacher":
        continue
    sched = httpx.get(f"{BASE}/api/schedule/user/{u['id']}", headers=M, timeout=30).json()
    for s in sched:
        httpx.delete(f"{BASE}/api/schedule/{s['id']}", headers=M, timeout=30)
    print(f"  {u['full_name']}: удалено {len(sched)}")

# Загружаем расписание с запросом «распределить всем»
print("\n=== Загрузка расписания с запросом «добавь всем преподавателям» ===")
if not os.path.exists(DOCX):
    print(f"  Файл не найден: {DOCX}")
else:
    with open(DOCX, "rb") as f:
        r = httpx.post(
            f"{BASE}/api/chat/upload",
            headers=M,
            files={"file": ("raspisanie.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            data={"message": "добавь всем преподавателям их пары"},
            timeout=600,
        )
    print(f"  HTTP {r.status_code}")
    res = r.json()
    print(f"  Статус: {res.get('status')}")
    print(f"  Сообщение:\n{res.get('message', '')[:900]}")

print("\n=== Что оказалось в календарях преподавателей ===")
total = 0
for u in users:
    if u.get("role") != "teacher":
        continue
    sched = httpx.get(f"{BASE}/api/schedule/user/{u['id']}", headers=M, timeout=30).json()
    total += len(sched)
    print(f"\n  {u['full_name']}: {len(sched)} пар")
    for s in sched[:5]:
        print(f"    {['Пн','Вт','Ср','Чт','Пт','Сб','Вс'][s['day_of_week']]} "
              f"{s['start_time']}–{s['end_time']} {s['title'][:40]:40} гр.{s['group_name']}")
    if len(sched) > 5:
        print(f"    … ещё {len(sched) - 5}")

print(f"\nВсего пар распределено: {total}")

# Повторная загрузка — должна всё пропустить как дубли
print("\n=== Повторная загрузка (проверка антидублей) ===")
if os.path.exists(DOCX):
    with open(DOCX, "rb") as f:
        r = httpx.post(
            f"{BASE}/api/chat/upload",
            headers=M,
            files={"file": ("raspisanie.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            data={"message": "добавь всем преподавателям их пары"},
            timeout=600,
        )
    res2 = r.json()
    print(f"  Сообщение:\n{res2.get('message', '')[:500]}")

    total2 = 0
    for u in users:
        if u.get("role") != "teacher":
            continue
        sched = httpx.get(f"{BASE}/api/schedule/user/{u['id']}", headers=M, timeout=30).json()
        total2 += len(sched)
    print(f"\n  Пар после повторной загрузки: {total2} (было {total})")
    print("  ✅ Дубли не добавились" if total2 == total else f"  ❌ Добавилось {total2 - total} дублей")