"""API-тест: задачи с периодами (день/месяц/год/без срока) + фильтры."""
import httpx, json

BASE = "http://localhost:8000"
r = httpx.post(f"{BASE}/api/auth/login", json={"username": "teacher", "password": "teacher"})
H = {"Authorization": f"Bearer {r.json()['access_token']}", "Content-Type": "application/json"}

# Уборка старых тестовых задач
for t in httpx.get(f"{BASE}/api/tasks/my", headers=H).json():
    if t["title"].startswith("API-"):
        httpx.delete(f"{BASE}/api/tasks/{t['id']}", headers=H)

print("=== Создание задач с разными периодами ===")
cases = [
    {"title": "API-Дневная", "scope": "day", "due_date": "2026-09-25"},
    {"title": "API-Месячная", "scope": "month", "due_month": "2026-10"},
    {"title": "API-Годовая", "scope": "year", "due_year": 2026},
    {"title": "API-БезСрока", "scope": "none"},
]
created = []
for c in cases:
    r = httpx.post(f"{BASE}/api/tasks/", headers=H, json=c, timeout=30)
    print(f"  {r.status_code} {c['title']}: scope={r.json().get('scope')} "
          f"date={r.json().get('due_date')} month={r.json().get('due_month')} year={r.json().get('due_year')}")
    assert r.status_code == 201, r.text
    created.append(r.json())

print("\n=== Нет поля priority в ответе ===")
assert "priority" not in created[0], "priority не должен возвращаться"
print("  OK: приоритет убран из API")

print("\n=== Список задач (сортировка: незавершённые по сроку) ===")
tasks = httpx.get(f"{BASE}/api/tasks/my", headers=H).json()
for t in tasks:
    print(f"  [{t['status']}] scope={t['scope']:6} {t['title']} "
          f"{t['due_date'] or t['due_month'] or t['due_year'] or '—'}")

print("\n=== Просрочка: задача на прошлый месяц ===")
r = httpx.post(f"{BASE}/api/tasks/", headers=H, json={
    "title": "API-Просроченная", "scope": "month", "due_month": "2020-01"
}, timeout=30)
past = r.json()
print(f"  создана: scope={past['scope']} month={past['due_month']}")

tasks = httpx.get(f"{BASE}/api/tasks/my", headers=H).json()
past_task = next(t for t in tasks if t["title"] == "API-Просроченная")
print(f"  статус в API: {past_task['status']} (ожидается overdue)")
assert past_task["status"] == "overdue", past_task["status"]

print("\n=== Смена периода: день -> год ===")
day_task = next(t for t in created if t["title"] == "API-Дневная")
r = httpx.put(f"{BASE}/api/tasks/{day_task['id']}", headers=H, json={
    "scope": "year", "due_year": 2027
}, timeout=30)
u = r.json()
print(f"  scope={u['scope']} year={u['due_year']} date={u['due_date']} (date должен стать None)")
assert u["scope"] == "year" and u["due_year"] == 2027 and u["due_date"] is None

print("\n=== Статус done фиксирует completed_at ===")
r = httpx.patch(f"{BASE}/api/tasks/{day_task['id']}/status", headers=H, json={"status": "done"}, timeout=30)
d = r.json()
print(f"  status={d['status']} completed_at={d['completed_at']}")
assert d["completed_at"] is not None

print("\n=== Возврат в работу сбрасывает completed_at ===")
r = httpx.patch(f"{BASE}/api/tasks/{day_task['id']}/status", headers=H, json={"status": "pending"}, timeout=30)
d2 = r.json()
print(f"  status={d2['status']} completed_at={d2['completed_at']} (ожидается None)")
assert d2["completed_at"] is None

print("\n=== Уборка ===")
for t in httpx.get(f"{BASE}/api/tasks/my", headers=H).json():
    if t["title"].startswith("API-"):
        httpx.delete(f"{BASE}/api/tasks/{t['id']}", headers=H)
print("  тестовые задачи удалены")

print("\nВСЕ API-ТЕСТЫ ПРОЙДЕНЫ")