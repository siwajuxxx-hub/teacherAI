"""Тест режима 1/2: преподаватель парсит свои пары из файла + отсечение дублей."""
import httpx, sys

BASE = "http://localhost:8000"
FILE = r"C:\Users\siwaj\.dsh\attachments\v1\files\af\af7b010845e044a9829941ee63419b5fd8e9904c8422498be6dea8427afb38f8\Raspisanie_zanyatiy_3_kursa_bakalavryi_zaochnaya_forma_obucheniya_(ustanovochnaya_sessiya).docx"

r = httpx.post(f"{BASE}/api/auth/login", json={"username": "gavrilov", "password": "gavrilov"})
if r.status_code != 200:
    print("Нет пользователя gavrilov:", r.status_code); sys.exit(1)
token = r.json()["access_token"]
H = {"Authorization": f"Bearer {token}"}

print("=== Парсинг в СВОЙ календарь (без запроса) ===")
with open(FILE, "rb") as f:
    r = httpx.post(f"{BASE}/api/chat/upload", headers=H,
                   files={"file": ("rasp.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
                   timeout=300)
print("Статус:", r.status_code)
if r.status_code != 200:
    print(r.text[:600]); sys.exit(1)

d = r.json()
print("message:", d.get("message"))
print("teacher:", d.get("teacher"))
print("items найдено:", len(d.get("items", [])))
print("skipped_duplicates:", d.get("skipped_duplicates"))
for it in d.get("items", [])[:5]:
    print(f"  [{it['day_of_week']}] {it['start_time']}-{it['end_time']} {it['title']} ауд.{it['room']}")

print("\n=== Текущее расписание в календаре ===")
sched = httpx.get(f"{BASE}/api/schedule/my", headers=H).json()
print(f"Записей: {len(sched)}")
for s in sched:
    print(f"  [{s['day_of_week']}] {s['start_time']}-{s['end_time']} {s['title']} ауд.{s['room']}")

# Проверяем уникальность
keys = set()
dups = 0
for s in sched:
    k = (s['title'].lower(), s['day_of_week'], s['start_time'], s['group_name'].lower())
    if k in keys:
        dups += 1
    keys.add(k)
print(f"\nДублей в календаре: {dups}")
if dups == 0:
    print("✅ Парсинг работает и дублей нет")
else:
    print("❌ Есть дубли")