"""Финальный тест: управляющий грузит расписание и распределяет по преподавателям.

Проверяет всю цепочку: запрос -> парсинг AI -> поиск учётной записи ->
добавление пар -> отсутствие дублей.
"""
import httpx, os, json

BASE = "http://localhost:8000"
DOCX = r"C:\Users\siwaj\.dsh\attachments\v1\files\af\af7b010845e044a9829941ee63419b5fd8e9904c8422498be6dea8427afb38f8\Raspisanie_zanyatiy_3_kursa_bakalavryi_zaochnaya_forma_obucheniya_(ustanovochnaya_sessiya).docx"


def login(u, p):
    r = httpx.post(f"{BASE}/api/auth/login", json={"username": u, "password": p})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


M = login("manager", "manager")

# ── 1. Смотрим текущие учётные записи ──
users = httpx.get(f"{BASE}/api/users/", headers=M, timeout=30).json()
teachers = {u["full_name"]: u for u in users if u.get("role") == "teacher"}
print("=== Преподаватели с учётными записями ===")
for name in teachers:
    print(f"  {name}")

# ── 2. Чистим их расписание ──
print("\n=== Уборка ===")
for name, u in teachers.items():
    sched = httpx.get(f"{BASE}/api/schedule/user/{u['id']}", headers=M, timeout=30).json()
    for s in sched:
        httpx.delete(f"{BASE}/api/schedule/{s['id']}", headers=M, timeout=30)
    print(f"  {name}: удалено {len(sched)}")

# ── 3. Загружаем РЕАЛЬНЫЙ файл с запросом «добавь всем» ──
print("\n=== Загрузка расписания (режим «всем преподавателям») ===")
if not os.path.exists(DOCX):
    print("  Файл не найден, пропускаем")
else:
    size = os.path.getsize(DOCX)
    print(f"  Файл: {size} байт")
    with open(DOCX, "rb") as f:
        r = httpx.post(
            f"{BASE}/api/chat/upload",
            headers=M,
            files={"file": ("raspisanie.docx", f,
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            data={"message": "добавь всем преподавателям их пары"},
            timeout=900,
        )
    print(f"  HTTP {r.status_code}")
    res = r.json()
    print(f"  Статус: {res.get('status')}")
    print(f"  Items извлечено: {len(res.get('items') or [])}")
    print(f"\n  Отчёт:\n{res.get('message', '')[:1200]}")

# ── 4. Что в календарях ──
print("\n=== Результат в календарях ===")
grand = 0
for name, u in teachers.items():
    sched = httpx.get(f"{BASE}/api/schedule/user/{u['id']}", headers=M, timeout=30).json()
    grand += len(sched)
    print(f"\n  {name}: {len(sched)} пар")
    for s in sched[:4]:
        d = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'][s['day_of_week']]
        print(f"    {d} {s['start_time']}–{s['end_time']} {s['title'][:35]:35} гр.{s['group_name']}")
    if len(sched) > 4:
        print(f"    … ещё {len(sched)-4}")

print(f"\n  ВСЕГО пар: {grand}")

# ── 5. Повтор — антидубли ──
print("\n=== Повторная загрузка (антидубли) ===")
if os.path.exists(DOCX):
    with open(DOCX, "rb") as f:
        r = httpx.post(
            f"{BASE}/api/chat/upload",
            headers=M,
            files={"file": ("raspisanie.docx", f,
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            data={"message": "добавь всем преподавателям их пары"},
            timeout=900,
        )
    res2 = r.json()
    print(f"  Отчёт:\n{res2.get('message', '')[:600]}")

    after = 0
    for name, u in teachers.items():
        after += len(httpx.get(f"{BASE}/api/schedule/user/{u['id']}", headers=M, timeout=30).json())
    print(f"\n  Пар после повтора: {after} (было {grand})")
    if after == grand:
        print("  ✅ Дубли НЕ добавились")
    else:
        print(f"  ❌ Добавилось {after - grand} дублей")

print("\n=== Проверка статистики по добавленным парам ===")
ov = httpx.get(f"{BASE}/api/stats/overview", headers=M, timeout=120).json()
for t in ov["teachers"]:
    if t["lessons_per_month"]:
        print(f"  {t['full_name']:28} пар/мес={t['lessons_per_month']:3} часов={t['hours_per_month']}")