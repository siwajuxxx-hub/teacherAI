"""РЕШАЮЩИЙ ТЕСТ: управляющий загружает расписание в чат и распределяет всем.

Проверяет три требования:
  1. Пары заносятся через чат управляющего
  2. Парсер обрабатывает ВСЕХ преподавателей из файла
  3. Пары получают только те, у кого ЕСТЬ учётная запись
"""
import httpx, os, sqlite3

BASE = "http://localhost:8000"
DOCX = r"C:\Users\siwaj\.dsh\attachments\v1\files\af\af7b010845e044a9829941ee63419b5fd8e9904c8422498be6dea8427afb38f8\Raspisanie_zanyatiy_3_kursa_bakalavryi_zaochnaya_forma_obucheniya_(ustanovochnaya_sessiya).docx"


def login(u, p):
    r = httpx.post(f"{BASE}/api/auth/login", json={"username": u, "password": p})
    r.raise_for_status()
    return {"Authorization": "Bearer " + r.json()["access_token"]}


A = login("admin", "admin")
M = login("manager", "manager")

# ─── 1. Убираем мусор из предыдущих тестов ───
print("=== Уборка расписания ===")
users = httpx.get(f"{BASE}/api/users/", headers=A, timeout=30).json()
for u in users:
    sched = httpx.get(f"{BASE}/api/schedule/user/{u['id']}", headers=M, timeout=30).json()
    for s in sched:
        httpx.delete(f"{BASE}/api/schedule/{s['id']}", headers=M, timeout=30)
    if sched:
        print(f"  {u['full_name']}: удалено {len(sched)}")

# ─── 2. Создаём учётные записи ДВУМ преподавателям из файла ───
# Певцова Л.С. и Гаврилов А.И. есть в расписании, но у них нет учёток.
# Черненкова А.А. — была за пределами старой обрезки, проверяем что теперь находится.
TEST = [
    {"username": "t_pevtsova", "password": "x12345", "full_name": "Певцова Л.С.",
     "position": "Ст. преподаватель", "role": "teacher"},
    {"username": "t_gavrilov", "password": "x12345", "full_name": "Гаврилов А.И.",
     "position": "Доцент", "role": "teacher"},
    {"username": "t_chernenkova", "password": "x12345", "full_name": "Черненкова А.А.",
     "position": "Доцент", "role": "teacher"},
]

print("\n=== Создание учётных записей ===")
ids = {}
for t in TEST:
    r = httpx.post(f"{BASE}/api/users/", headers=A, json=t, timeout=30)
    if r.status_code in (200, 201):
        ids[t["full_name"]] = r.json()["id"]
        print(f"  ✅ {t['full_name']}")
    else:
        print(f"  ⚠ {t['full_name']}: {r.status_code} {r.text[:120]}")

# ─── 3. Загружаем расписание в режиме «всем» ───
print("\n=== Загрузка расписания с запросом «добавь всем преподавателям их пары» ===")
with open(DOCX, "rb") as f:
    r = httpx.post(
        f"{BASE}/api/chat/upload", headers=M,
        files={"file": ("raspisanie.docx", f,
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        data={"message": "добавь всем преподавателям их пары"},
        timeout=900,
    )

print(f"  HTTP {r.status_code}")
if r.status_code != 200:
    print(f"  ❌ Ошибка: {r.text[:400]}")
    raise SystemExit(1)

res = r.json()
print(f"  Статус: {res.get('status')}")
print(f"  Преподавателей найдено: {res.get('teachers_found')}")
print(f"  Пар добавлено: {res.get('total_added')}")
print(f"  Пропущено дублей: {res.get('total_skipped')}")
nf = res.get('not_found') or []
print(f"  Без учётной записи: {len(nf)}")
print(f"\n  Отчёт:\n{res.get('message','')[:900]}")

# ─── 4. Проверяем результат ───
print("\n=== Пары в календарях ===")
ok, fail = [], []
for name, uid in ids.items():
    sched = httpx.get(f"{BASE}/api/schedule/user/{uid}", headers=M, timeout=30).json()
    if sched:
        ok.append(name)
        print(f"\n  {name}: {len(sched)} пар")
        for s in sched[:5]:
            d = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'][s['day_of_week']]
            print(f"    {d} {s['start_time']}–{s['end_time']} {s['title'][:38]:38} гр.{s['group_name']}")
        if len(sched) > 5:
            print(f"    … ещё {len(sched)-5}")
    else:
        fail.append(name)
        print(f"\n  {name}: 0 пар")

print(f"\n  Получили пары: {ok}")
if fail:
    print(f"  НЕ получили: {fail}")

# ─── 5. Убеждаемся, что парсер покрыл всех ───
print("\n=== Проверка: все ли преподаватели из файла распознаны ===")
print(f"  Распознано парсером: {res.get('teachers_found', 0)} с учётками + {len(nf)} без")
total_parsed = res.get('teachers_found', 0) + len(nf)
print(f"  Итого преподавателей из файла: {total_parsed} (в файле 24-25)")
if total_parsed >= 24:
    print("  ✅ Парсер покрыл ВСЕХ преподавателей (чанкование работает)")
else:
    print(f"   Распознано только {total_parsed} — часть потерялась")

# ─── 6. Повторная загрузка ───
print("\n=== Повторная загрузка (антидубли) ===")
with open(DOCX, "rb") as f:
    r2 = httpx.post(
        f"{BASE}/api/chat/upload", headers=M,
        files={"file": ("raspisanie.docx", f,
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        data={"message": "добавь всем преподавателям их пары"},
        timeout=900,
    )
res2 = r2.json()
print(f"  Добавлено при повторе: {res2.get('total_added')} (ожидается 0)")
print(f"  Пропущено дублей: {res2.get('total_skipped')}")

after = sum(len(httpx.get(f"{BASE}/api/schedule/user/{u}", headers=M, timeout=30).json())
            for u in ids.values())
print(f"  Пар всего после повтора: {after}")
print("  ✅ Дубли НЕ добавились" if res2.get('total_added') == 0 else "  ❌ Появились дубли")

# ─── 7. Статистика ──
print("\n=== Статистика по добавленным парам ===")
ov = httpx.get(f"{BASE}/api/stats/overview", headers=M, timeout=120).json()
for t in ov["teachers"]:
    if t["lessons_per_month"] or t["has_schedule"]:
        print(f"  {t['full_name']:26} пар/мес={t['lessons_per_month']:3} часов/мес={t['hours_per_month']}")

print("\n✅ ТЕСТ ЗАВЕРШЁН")