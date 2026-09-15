"""Сквозной тест: управляющий загружает файл -> распределение с проверкой дублей."""
import httpx, json, sys

BASE = "http://localhost:8000"
FILE = r"C:\Users\siwaj\.dsh\attachments\v1\files\af\af7b010845e044a9829941ee63419b5fd8e9904c8422498be6dea8427afb38f8\Raspisanie_zanyatiy_3_kursa_bakalavryi_zaochnaya_forma_obucheniya_(ustanovochnaya_sessiya).docx"

r = httpx.post(f"{BASE}/api/auth/login", json={"username": "manager", "password": "manager"})
if r.status_code != 200:
    print("Не удалось войти как manager:", r.status_code, r.text[:200]); sys.exit(1)
token = r.json()["access_token"]
H = {"Authorization": f"Bearer {token}"}

print("=== Загрузка 1: распределить всем преподавателям ===")
with open(FILE, "rb") as f:
    r = httpx.post(f"{BASE}/api/chat/upload", headers=H,
                   files={"file": ("rasp.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
                   data={"message": "добавь всем преподавателям их пары"}, timeout=300)
print("Статус:", r.status_code)
if r.status_code != 200:
    print(r.text[:800]); sys.exit(1)
d1 = r.json()
print("Сообщение:\n" + d1.get("message", "")[:1500])
print(f"\nteachers_found={d1.get('teachers_found')} total_added={d1.get('total_added')} "
      f"total_skipped={d1.get('total_skipped')} not_found={d1.get('not_found')}")
first_added = d1.get("total_added", 0)

print("\n=== Загрузка 2: тот же файл повторно (всё должно быть дублями) ===")
with open(FILE, "rb") as f:
    r = httpx.post(f"{BASE}/api/chat/upload", headers=H,
                   files={"file": ("rasp.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
                   data={"message": "добавь всем преподавателям их пары"}, timeout=300)
print("Статус:", r.status_code)
d2 = r.json()
print("Сообщение:\n" + d2.get("message", "")[:1500])
second_added = d2.get("total_added", 0)

print("\n=== ИТОГ ===")
print(f"Первый импорт добавил:  {first_added}")
print(f"Второй импорт добавил:  {second_added}  (ожидается 0 — все дубли)")
if second_added == 0:
    print("✅ Дубли не создаются")
else:
    print("❌ Дубли создаются — проверьте логику")