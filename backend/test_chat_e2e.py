"""Сквозной тест: чат -> AI -> действия -> выполнение."""
import httpx, json

BASE = "http://localhost:8000"

r = httpx.post(f"{BASE}/api/auth/login", json={"username": "teacher", "password": "teacher"})
token = r.json()["access_token"]
H = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

print("=== 1. Просим AI создать задачу ===")
actions = []
text = ""
with httpx.stream("POST", f"{BASE}/api/chat/send", headers=H,
                  json={"message": "Добавь задачу «Проверить лабораторные» на 25 сентября, приоритет высокий"},
                  timeout=120) as resp:
    for line in resp.iter_lines():
        if line.startswith("data: "):
            d = json.loads(line[6:])
            if d.get("chunk"):
                text += d["chunk"]
            if d.get("actions"):
                actions = d["actions"]

print("Ответ AI:", text[:300])
print("Действия:", json.dumps(actions, ensure_ascii=False, indent=2) if actions else "НЕТ")

if not actions:
    print("\n⚠️ AI не вернул действий — проверьте ключ/модель")
    raise SystemExit(1)

print("\n=== 2. Подтверждаем действия ===")
r = httpx.post(f"{BASE}/api/chat/execute-actions", headers=H, json={"actions": actions}, timeout=60)
print("Статус:", r.status_code)
print(json.dumps(r.json(), ensure_ascii=False, indent=2))

print("\n=== 3. Проверяем задачи ===")
tasks = httpx.get(f"{BASE}/api/tasks/my", headers=H).json()
found = [t for t in tasks if "лабораторн" in t["title"].lower()]
for t in found:
    print(f"  [{t['status']}] {t['title']} срок={t['due_date']} приоритет={t['priority']}")

if found:
    print("\n=== 4. Просим AI отметить как выполненную ===")
    actions2 = []
    text2 = ""
    with httpx.stream("POST", f"{BASE}/api/chat/send", headers=H,
                      json={"message": f"Отметь задачу «{found[0]['title']}» как выполненную"}, timeout=120) as resp:
        for line in resp.iter_lines():
            if line.startswith("data: "):
                d = json.loads(line[6:])
                if d.get("chunk"):
                    text2 += d["chunk"]
                if d.get("actions"):
                    actions2 = d["actions"]
    print("Ответ AI:", text2[:200])
    print("Действия:", [a["description"] for a in actions2] if actions2 else "НЕТ")
    if actions2:
        r = httpx.post(f"{BASE}/api/chat/execute-actions", headers=H, json={"actions": actions2}, timeout=60)
        print("Результат:", r.json()["report"])

    # Уборка
    for t in found:
        httpx.delete(f"{BASE}/api/tasks/{t['id']}", headers=H)
    print("\n(тестовые задачи удалены)")

print("\n=== 5. Проверяем расписание / перенос пары ===")
sched = httpx.get(f"{BASE}/api/schedule/my", headers=H).json()
print(f"Записей в календаре: {len(sched)}")
for s in sched[:3]:
    print(f"  [{s['day_of_week']}] {s['title']} {s['start_time']}-{s['end_time']} ауд.{s['room']}")

if sched:
    target = sched[0]["title"]
    actions3 = []
    text3 = ""
    with httpx.stream("POST", f"{BASE}/api/chat/send", headers=H,
                      json={"message": f"Перенеси пару «{target}» на пятницу и смени аудиторию на 777"}, timeout=120) as resp:
        for line in resp.iter_lines():
            if line.startswith("data: "):
                d = json.loads(line[6:])
                if d.get("chunk"):
                    text3 += d["chunk"]
                if d.get("actions"):
                    actions3 = d["actions"]
    print("Ответ AI:", text3[:200])
    print("Действия:", [a["description"] for a in actions3] if actions3 else "НЕТ")
    if actions3:
        r = httpx.post(f"{BASE}/api/chat/execute-actions", headers=H, json={"actions": actions3}, timeout=60)
        print("Результат:", r.json()["report"])
