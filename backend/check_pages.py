"""Финальная проверка страниц управляющего."""
import httpx

r = httpx.post('http://localhost:8000/api/auth/login',
               json={'username': 'manager', 'password': 'manager'})
H = {'Authorization': 'Bearer ' + r.json()['access_token']}

print('=== Страница «Обзор» ===')
o = httpx.get('http://localhost:8000/api/stats/overview', headers=H, timeout=60).json()
print(f"  Период: {o['month']:02d}.{o['year']}")
t = o['totals']
print(f"  Итоги: преподавателей={t['teachers_total']} (с расписанием {t['teachers_with_schedule']})")
print(f"         пар/мес={t['lessons_per_month']}, часов/мес={t['hours_per_month']}")
print(f"         задач={t['tasks_total']} (выполнено {t['tasks_done']}, просрочено {t['tasks_overdue']}, {t['completion_rate']}%)")
print(f"  Таблица: {len(o['teachers'])} строк")

print()
print('=== Страница «Календарь» ===')
c = httpx.get('http://localhost:8000/api/stats/calendar', headers=H,
              params={'year': o['year'], 'month': o['month']}, timeout=60).json()
print(f"  Выпадающий список преподавателей: {len(c['teachers'])}")
for tt in c['teachers']:
    print(f"    - {tt['full_name']}")
print(f"  Дней с событиями: {len(c['days'])}")
print(f"  Пар всего: {sum(len(d['lessons']) for d in c['days'])}")
print(f"  Задач всего: {sum(len(d['tasks']) for d in c['days'])}")

print()
print('=== Фильтр «только этот преподаватель» ===')
tid = c['teachers'][0]['id']
c2 = httpx.get('http://localhost:8000/api/stats/calendar', headers=H,
               params={'year': o['year'], 'month': o['month'], 'teacher_id': tid}, timeout=60).json()
print(f"  Преподавателей: {len(c2['teachers'])} — {c2['teachers'][0]['full_name']}")
print(f"  Его пар: {sum(len(d['lessons']) for d in c2['days'])}")
print(f"  Его задач: {sum(len(d['tasks']) for d in c2['days'])}")
assert len(c2['teachers']) == 1

print()
print('=== Детали преподавателя + разбивка по месяцам ===')
d = httpx.get(f'http://localhost:8000/api/stats/teacher/{tid}', headers=H,
              params={'year': o['year'], 'month': o['month']}, timeout=60).json()
print(f"  {d['teacher']['full_name']}: пар/мес={d['lessons_per_month']}, часов={d['hours_per_month']}, "
      f"задач={d['tasks_total']}")
m = httpx.get(f'http://localhost:8000/api/stats/teacher/{tid}/monthly', headers=H,
              params={'year': o['year']}, timeout=60).json()
print(f"  Месяцев в году: {len(m['months'])}")

print()
print('✅ ОБЕ СТРАНИЦЫ РАБОТАЮТ')