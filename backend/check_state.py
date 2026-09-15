"""Проверка состояния AI и возможности восстановления расписания."""
import httpx, sqlite3

# Настройки AI
c = sqlite3.connect("data/auth.db")
cur = c.cursor()
cur.execute("SELECT key, substr(value,1,60) FROM app_settings")
print("=== Настройки AI ===")
for k, v in cur.fetchall():
    print(f"  {k} = {v}")
c.close()

# Размер расписания
c = sqlite3.connect("data/data.db")
cur = c.cursor()
cur.execute("SELECT COUNT(*) FROM schedules")
print(f"\n=== Состояние данных ===")
print(f"  Пар в расписании: {cur.fetchone()[0]}")
cur.execute("SELECT COUNT(*) FROM tasks")
print(f"  Задач: {cur.fetchone()[0]}")
cur.execute("SELECT user_id, COUNT(*) FROM tasks GROUP BY user_id")
print("  Задачи по пользователям:", cur.fetchall())
c.close()

# Проверка, жив ли AI (лимит)
r = httpx.post('http://localhost:8000/api/auth/login',
               json={'username': 'manager', 'password': 'manager'})
H = {'Authorization': 'Bearer ' + r.json()['access_token']}
print("\n=== Проверка лимита AI ===")
resp = httpx.post('http://localhost:8000/api/chat/send', headers=H,
                  json={'message': 'привет'}, timeout=120)
print(f"  HTTP {resp.status_code}")
text = resp.text[:300]
if 'limit' in text.lower() or '429' in text:
    print("  ⚠ Лимит AI всё ещё исчерпан")
    print(f"  {text}")
else:
    print(f"  AI отвечает: {text[:150]}")