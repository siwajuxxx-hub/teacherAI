"""Тест: управляющий меняет преподавателя у пары через действия чата."""
import httpx, json

BASE = "http://localhost:8000"

# Вход управляющим
r = httpx.post(f"{BASE}/api/auth/login", json={"username": "manager", "password": "manager"})
H = {"Authorization": f"Bearer {r.json()['access_token']}", "Content-Type": "application/json"}

# Вход преподавателем (gavrilov) — создадим пару
r = httpx.post(f"{BASE}/api/auth/login", json={"username": "gavrilov", "password": "gavrilov"})
HT = {"Authorization": f"Bearer {r.json()['access_token']}", "Content-Type": "application/json"}

print("=== Создаём пару у gavrilov ===")
r = httpx.post(f"{BASE}/api/schedule/", headers=HT, json={
    "title": "Тестовая пара для передачи", "day_of_week": 1,
    "start_time": "09:00", "end_time": "10:30",
    "group_name": "ТЕСТ-ГР", "room": "100", "type": "lesson",
}, timeout=30)
print("Статус:", r.status_code)
sid = r.json()["id"]
gav_id = r.json()["user_id"]
print(f"id={sid} user_id={gav_id}")

print("\n=== Управляющий передаёт пару преподавателю teacher ===")
actions = [{
    "action": "update_schedule",
    "params": {"title": "Тестовая пара для передачи", "teacher_name": "Мария Ивановна", "room": "202"},
}]
r = httpx.post(f"{BASE}/api/chat/execute-actions", headers=H, json={"actions": actions}, timeout=60)
print("Статус:", r.status_code)
print(json.dumps(r.json(), ensure_ascii=False, indent=2))

print("\n=== Проверяем, что пара ушла от gavrilov ===")
r = httpx.get(f"{BASE}/api/schedule/my", headers=HT)
still = [s for s in r.json() if s["id"] == sid]
print(f"Осталась у gavrilov: {len(still)} (ожидается 0)")
if not still:
    print("✅ Пара передана другому преподавателю")
else:
    print("❌ Пара не передана")

# Уборка
r = httpx.post(f"{BASE}/api/auth/login", json={"username": "teacher", "password": "teacher"})
HT2 = {"Authorization": f"Bearer {r.json()['access_token']}"}
sched = httpx.get(f"{BASE}/api/schedule/my", headers=HT2).json()
for s in sched:
    if s["title"] == "Тестовая пара для передачи":
        httpx.delete(f"{BASE}/api/schedule/{s['id']}", headers=HT2)
        print("\n(тестовая пара удалена у нового владельца)")