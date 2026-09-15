"""Проверка состояния: данные, AI, эндпоинты."""
import httpx, sqlite3, json

print("=== Состояние БД ===")
c = sqlite3.connect("data/data.db")
cur = c.cursor()
cur.execute("SELECT COUNT(*) FROM schedules")
print(f"  Пар в расписании: {cur.fetchone()[0]}")
cur.execute("SELECT COUNT(*) FROM tasks")
print(f"  Задач: {cur.fetchone()[0]}")
cur.execute("SELECT DISTINCT scope FROM tasks")
print(f"  Периоды задач: {[r[0] for r in cur.fetchall()]}")
c.close()

c = sqlite3.connect("data/auth.db")
cur = c.cursor()
cur.execute("SELECT username, full_name, role FROM users")
print("\n=== Учётные записи ===")
for u, f, r in cur.fetchall():
    print(f"  {u:10} {f:26} {r}")
c.close()

print("\n=== Эндпоинты ===")
r = httpx.post('http://localhost:8000/api/auth/login',
               json={'username': 'manager', 'password': 'manager'})
H = {'Authorization': 'Bearer ' + r.json()['access_token']}

for path, params in [
    ('/api/stats/overview', None),
    ('/api/stats/calendar', {'year': 2026, 'month': 9}),
    ('/api/stats/all-load', None),
    ('/api/users/', None),
    ('/api/schedule/my', None),
    ('/api/tasks/my', None),
]:
    try:
        resp = httpx.get(f'http://localhost:8000{path}', headers=H, params=params, timeout=60)
        body = resp.text[:120].replace('\n', ' ')
        print(f"  {resp.status_code}  {path:32} {body}")
    except Exception as e:
        print(f"  ERR {path:32} {e}")

print("\n=== Доступность AI ===")
try:
    with httpx.stream('POST', 'http://localhost:8000/api/chat/send', headers=H,
                      json={'message': 'привет'}, timeout=120) as resp:
        text = ''
        for line in resp.iter_lines():
            if line.startswith('data: '):
                d = json.loads(line[6:])
                if d.get('chunk'):
                    text += d['chunk']
        if '429' in text or 'Rate limit' in text:
            print("  ⚠ AI-лимит исчерпан (бесплатные запросы закончились)")
        else:
            print(f"  ✅ AI работает: {text[:150]}")
except Exception as e:
    print(f"  ERR: {e}")