"""Сквозной тест чата: постановка задач на день/месяц/год через AI."""
import httpx, json, sys

BASE = "http://localhost:8000"
r = httpx.post(f"{BASE}/api/auth/login", json={"username": "teacher", "password": "teacher"})
H = {"Authorization": f"Bearer {r.json()['access_token']}", "Content-Type": "application/json"}

# Уборка
for t in httpx.get(f"{BASE}/api/tasks/my", headers=H).json():
    httpx.delete(f"{BASE}/api/tasks/{t['id']}", headers=H)


def chat(msg):
    """Отправляет сообщение и возвращает (текст, действия)."""
    text, actions = "", []
    with httpx.stream("POST", f"{BASE}/api/chat/send", headers=H,
                      json={"message": msg}, timeout=180) as resp:
        for line in resp.iter_lines():
            if line.startswith("data: "):
                d = json.loads(line[6:])
                if d.get("chunk"):
                    text += d["chunk"]
                if d.get("final_text"):
                    text = d["final_text"]
                if d.get("actions"):
                    actions = d["actions"]
    return text, actions


requests = [
    "Добавь задачу проверить лабораторные работы на 28 сентября",
    "Поставь задачу подготовить отчёт за октябрь",
    "Добавь задачу пройти курсы повышения квалификации на 2026 год",
]

print("=== Постановка задач через чат ===")
for msg in requests:
    text, actions = chat(msg)
    print(f"\nЗапрос: {msg}")
    print(f"  Ответ AI: {text[:120].strip()}")
    if not actions:
        print("  ❌ ДЕЙСТВИЙ НЕТ — задача потерялась!")
        continue
    for a in actions:
        print(f"  → {a['description']}")

    r = httpx.post(f"{BASE}/api/chat/execute-actions", headers=H,
                   json={"actions": actions}, timeout=60)
    print(f"  Результат: {r.json()['report']}")

print("\n=== Что в заметках ===")
tasks = httpx.get(f"{BASE}/api/tasks/my", headers=H).json()
for t in tasks:
    due = t["due_date"] or t["due_month"] or t["due_year"] or "без срока"
    print(f"  [{t['status']}] scope={t['scope']:5} «{t['title']}» — {due}")

print(f"\nВсего задач: {len(tasks)} (ожидается 3)")
if len(tasks) == 3:
    print("✅ Все задачи из чата сохранены, ни одна не потерялась")
else:
    print("❌ Часть задач потерялась")

print("\n=== Уборка ===")
for t in tasks:
    httpx.delete(f"{BASE}/api/tasks/{t['id']}", headers=H)
print("  готово")