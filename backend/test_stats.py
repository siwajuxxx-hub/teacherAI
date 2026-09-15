"""Тест статистики и календаря управляющего."""
import httpx

BASE = "http://localhost:8000"

def login(u, p):
    r = httpx.post(f"{BASE}/api/auth/login", json={"username": u, "password": p})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}

M = login("manager", "manager")
A = login("admin", "admin")
T = login("teacher", "teacher")

print("=== 1. Обзор (manager) ===")
r = httpx.get(f"{BASE}/api/stats/overview", headers=M, timeout=60)
print(f"  {r.status_code}")
d = r.json()
print(f"  Период: {d['month']:02d}.{d['year']}")
print(f"  Всего преподавателей: {d['totals']['teachers_total']}")
print(f"  С расписанием: {d['totals']['teachers_with_schedule']}")
print(f"  Пар за месяц: {d['totals']['lessons_per_month']}")
print(f"  Часов за месяц: {d['totals']['hours_per_month']}")
print(f"  Задач: {d['totals']['tasks_total']} (выполнено {d['totals']['tasks_done']}, просрочено {d['totals']['tasks_overdue']})")
print(f"  Выполнение: {d['totals']['completion_rate']}%")
print("\n  По преподавателям:")
for t in d["teachers"]:
    print(f"    {t['full_name']:35} пар/мес={t['lessons_per_month']:3} ч={t['hours_per_month']:6} "
          f"задач={t['tasks_total']:2} выполн={t['tasks_done']:2} просроч={t['tasks_overdue']:2} "
          f"{'[есть расписание]' if t['has_schedule'] else '[нет расписания]'}")

assert d["totals"]["teachers_total"] > 0, "нет преподавателей"

print("\n=== 2. Календарь управляющего (все преподаватели) ===")
r = httpx.get(f"{BASE}/api/stats/calendar", headers=M,
              params={"year": d["year"], "month": d["month"]}, timeout=60)
c = r.json()
print(f"  {r.status_code} преподавателей: {len(c['teachers'])}")
print(f"  Дней с событиями: {len(c['days'])}")
total_lessons = sum(len(x["lessons"]) for x in c["days"])
total_tasks = sum(len(x["tasks"]) for x in c["days"])
print(f"  Пар всего: {total_lessons}, задач: {total_tasks}")

# Показываем первые 3 дня с парами
shown = 0
for day in c["days"]:
    if day["lessons"] and shown < 3:
        print(f"\n  {day['date']}:")
        for l in day["lessons"][:4]:
            print(f"    {l['start_time']}–{l['end_time']} {l['teacher_name']:30} "
                  f"{l['title'][:35]:35} гр.{l['group_name']} ауд.{l['room']}")
        shown += 1

print("\n=== 3. Календарь по одному преподавателю ===")
teacher_id = None
if c["teachers"]:
    teacher_id = c["teachers"][0]["id"]
    r = httpx.get(f"{BASE}/api/stats/calendar", headers=M,
                  params={"year": d["year"], "month": d["month"], "teacher_id": teacher_id}, timeout=60)
    c2 = r.json()
    n_l = sum(len(x["lessons"]) for x in c2["days"])
    n_t = sum(len(x["tasks"]) for x in c2["days"])
    print(f"  {c2['teachers'][0]['full_name']}: пар={n_l} задач={n_t}")
    assert len(c2["teachers"]) == 1, "фильтр не сработал"

print("\n=== 4. Детали по преподавателю ===")
r = httpx.get(f"{BASE}/api/stats/teacher/{teacher_id}", headers=M,
              params={"year": d["year"], "month": d["month"]}, timeout=60)
det = r.json()
print(f"  {r.status_code} {det['teacher']['full_name']}: "
      f"пар/мес={det['lessons_per_month']} ч={det['hours_per_month']} "
      f"задач={det['tasks_total']} выполн={det['tasks_done']}")

print("\n=== 5. Разбивка по месяцам ===")
r = httpx.get(f"{BASE}/api/stats/teacher/{teacher_id}/monthly", headers=M,
              params={"year": d["year"]}, timeout=60)
mo = r.json()
print(f"  {r.status_code} месяцев: {len(mo['months'])}")
for m in mo["months"]:
    if m["lessons"] or m["tasks_total"]:
        print(f"    {m['month']:2}: пар={m['lessons']:3} ч={m['hours']:6} задач={m['tasks_total']:2} выполн={m['tasks_done']:2}")

print("\n=== 6. Доступ: преподаватель НЕ должен видеть статистику ===")
r = httpx.get(f"{BASE}/api/stats/overview", headers=T, timeout=30)
print(f"  teacher -> {r.status_code} (ожидается 403)")
assert r.status_code == 403, f"преподаватель получил доступ: {r.status_code}"

print("\n=== 7. Доступ: админ тоже может ===")
r = httpx.get(f"{BASE}/api/stats/overview", headers=A, timeout=60)
print(f"  admin -> {r.status_code}")
assert r.status_code == 200

print("\nВСЕ ТЕСТЫ СТАТИСТИКИ ПРОЙДЕНЫ")