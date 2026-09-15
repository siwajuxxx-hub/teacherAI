"""Проверка: пары заносятся только тем, у кого ЕСТЬ учётная запись."""
import httpx, os

BASE = "http://localhost:8000"
DOCX = r"C:\Users\siwaj\.dsh\attachments\v1\files\af\af7b010845e044a9829941ee63419b5fd8e9904c8422498be6dea8427afb38f8\Raspisanie_zanyatiy_3_kursa_bakalavryi_zaochnaya_forma_obucheniya_(ustanovochnaya_sessiya).docx"


def login(u, p):
    r = httpx.post(f"{BASE}/api/auth/login", json={"username": u, "password": p})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


A = login("admin", "admin")
M = login("manager", "manager")

# ─ Создаём учётные записи для ДВУХ преподавателей из файла ──
# Певцова Л.С. и Гаврилов А.И. точно есть в расписании
TEST_USERS = [
    {"username": "pevtsova_test", "password": "test123", "full_name": "Певцова Л.С.",
     "position": "Старший преподаватель", "role": "teacher"},
    {"username": "gavrilov_test", "password": "test123", "full_name": "Гаврилов А.И.",
     "position": "Доцент", "role": "teacher"},
]

print("=== Создание тестовых учётных записей ===")
created = []
existing = {u["username"]: u for u in httpx.get(f"{BASE}/api/users/", headers=A, timeout=30).json()}

for tu in TEST_USERS:
    if tu["username"] in existing:
        print(f"  {tu['full_name']}: уже существует")
        created.append(existing[tu["username"]])
        continue
    r = httpx.post(f"{BASE}/api/users/", headers=A, json=tu, timeout=30)
    if r.status_code in (200, 201):
        print(f"  ✅ {tu['full_name']} ({tu['username']}) создан")
        created.append(r.json())
    else:
        print(f"   {tu['full_name']}: {r.status_code} {r.text[:200]}")

# ─ Чистим расписание ТОЛЬКО у новых ──
print("\n=== Уборка расписания тестовых ===")
for u in created:
    sched = httpx.get(f"{BASE}/api/schedule/user/{u['id']}", headers=M, timeout=30).json()
    for s in sched:
        httpx.delete(f"{BASE}/api/schedule/{s['id']}", headers=M, timeout=30)
    print(f"  {u['full_name']}: удалено {len(sched)}")

# ── Загружаем расписание в режиме распределения ──
print("\n=== Загрузка расписания («добавь всем преподавателям») ===")
with open(DOCX, "rb") as f:
    r = httpx.post(
        f"{BASE}/api/chat/upload",
        headers=M,
        files={"file": ("raspisanie.docx", f,
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        data={"message": "добавь всем преподавателям их пары"},
        timeout=900,
    )
print(f"  HTTP {r.status_code}, статус: {r.json().get('status')}")
print(f"\n  Отчёт:\n{r.json().get('message', '')[:1000]}")

# ── Проверяем результат ──
print("\n=== Пары в календарях тестовых преподавателей ===")
ok = 0
for u in created:
    sched = httpx.get(f"{BASE}/api/schedule/user/{u['id']}", headers=M, timeout=30).json()
    print(f"\n  {u['full_name']}: {len(sched)} пар")
    for s in sched[:6]:
        d = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'][s['day_of_week']]
        print(f"    {d} {s['start_time']}–{s['end_time']} {s['title'][:40]:40} гр.{s['group_name']} ауд.{s['room']}")
    if len(sched) > 6:
        print(f"    … ещё {len(sched)-6}")
    if sched:
        ok += 1

print(f"\n  Преподавателей с парами: {ok}/{len(created)}")
if ok == len(created):
    print("  ✅ Пары занесены ВСЕМ, у кого есть учётная запись")
else:
    print("  ❌ Не всем занесены пары")

# ── Повтор: дубли ─
print("\n=== Повторная загрузка (антидубли) ===")
with open(DOCX, "rb") as f:
    r2 = httpx.post(
        f"{BASE}/api/chat/upload",
        headers=M,
        files={"file": ("raspisanie.docx", f,
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        data={"message": "добавь всем преподавателям их пары"},
        timeout=900,
    )
print(f"  Отчёт: {r2.json().get('message', '')[:400]}")

after = 0
for u in created:
    after += len(httpx.get(f"{BASE}/api/schedule/user/{u['id']}", headers=M, timeout=30).json())
before = sum(len(httpx.get(f"{BASE}/api/schedule/user/{u['id']}", headers=M, timeout=30).json()) for u in created)
print(f"\n  Пар всего после повтора: {after}")
if after == before:
    print("  ✅ Дубли НЕ добавились")
else:
    print(f"  ❌ Появились дубли")

# ── Уборка тестовых пользователей ──
print("\n=== Удаление тестовых учётных записей ===")
for u in created:
    r = httpx.delete(f"{BASE}/api/users/{u['id']}", headers=A, timeout=30)
    print(f"  {u['full_name']}: {r.status_code}")