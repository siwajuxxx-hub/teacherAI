"""Test: chat tools — create task, update status, etc."""
import httpx, json, time

BASE = "http://localhost:8000"

def login(u, p):
    r = httpx.post(f"{BASE}/api/auth/login", json={"username": u, "password": p})
    return r.json()["access_token"]

token = login("teacher", "teacher")
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# Test 1: Create a task via chat
print("=== Test 1: Create task ===")
with httpx.stream("POST", f"{BASE}/api/chat/send", headers=headers,
                  json={"message": "Создай задачу «Проверить тетради» на завтра со средним приоритетом"}, timeout=90) as resp:
    full = ""
    for line in resp.iter_lines():
        if line.startswith("data: "):
            data = json.loads(line[6:])
            if data.get("chunk"):
                full += data["chunk"]
            if data.get("tool_results"):
                for r in data["tool_results"]:
                    print(f"  TOOL: {r}")

print(f"  AI response: {full[:200]}")

# Check task was created
print("\n=== Verifying task ===")
tasks = httpx.get(f"{BASE}/api/tasks/my", headers={"Authorization": f"Bearer {token}"}).json()
for t in tasks:
    print(f"  [{t['status']}] {t['title']} due={t.get('due_date','-')}")

# Test 2: Update task status
print("\n=== Test 2: Mark task done ===")
if tasks:
    target = tasks[0]["title"]
    with httpx.stream("POST", f"{BASE}/api/chat/send", headers=headers,
                      json={"message": f"Отметь задачу «{target}» как выполненную"}, timeout=90) as resp:
        full = ""
        for line in resp.iter_lines():
            if line.startswith("data: "):
                data = json.loads(line[6:])
                if data.get("chunk"):
                    full += data["chunk"]
                if data.get("tool_results"):
                    print("  TOOL:", data["tool_results"])

print("\n=== Test 3: Add schedule ===")
with httpx.stream("POST", f"{BASE}/api/chat/send", headers=headers,
                  json={"message": "Добавь пару «Консультация» в среду с 14:00 до 15:30, ауд. 401"}, timeout=90) as resp:
    full = ""
    for line in resp.iter_lines():
        if line.startswith("data: "):
            data = json.loads(line[6:])
            if data.get("chunk"):
                full += data["chunk"]
            if data.get("tool_results"):
                for r in data["tool_results"]:
                    print(f"  TOOL: {r}")

sched = httpx.get(f"{BASE}/api/schedule/my", headers={"Authorization": f"Bearer {token}"}).json()
for s in sched:
    print(f"  [{s['day_of_week']}] {s['title']} {s['start_time']}-{s['end_time']} ауд.{s['room']}")