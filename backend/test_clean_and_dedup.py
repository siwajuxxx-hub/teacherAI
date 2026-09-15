"""Очистка календаря тестового преподавателя и повторная проверка дедупликации."""
import asyncio, httpx
from sqlalchemy import select, delete
from app.database import init_databases, DataSessionLocal, AuthSessionLocal
from app.models.data_models import Schedule
from app.models.auth_models import User

FILE = r"C:\Users\siwaj\.dsh\attachments\v1\files\af\af7b010845e044a9829941ee63419b5fd8e9904c8422498be6dea8427afb38f8\Raspisanie_zanyatiy_3_kursa_bakalavryi_zaochnaya_forma_obucheniya_(ustanovochnaya_sessiya).docx"
BASE = "http://localhost:8000"


async def clean(username: str):
    await init_databases()
    async with AuthSessionLocal() as s:
        r = await s.execute(select(User).where(User.username == username))
        u = r.scalar_one_or_none()
        if not u:
            print(f"  {username}: нет пользователя")
            return
    async with DataSessionLocal() as db:
        await db.execute(delete(Schedule).where(Schedule.user_id == u.id))
        await db.commit()
    print(f"  {username}: календарь очищен")


def upload(username, password, message=None):
    r = httpx.post(f"{BASE}/api/auth/login", json={"username": username, "password": password})
    token = r.json()["access_token"]
    H = {"Authorization": f"Bearer {token}"}
    data = {"message": message} if message else {}
    with open(FILE, "rb") as f:
        r = httpx.post(f"{BASE}/api/chat/upload", headers=H,
                       files={"file": ("r.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
                       data=data, timeout=300)
    return r.json()


async def main():
    print("=== Очистка ===")
    for u in ("gavrilov", "teacher"):
        await clean(u)

    print("\n=== Импорт 1 (gavrilov, свои пары) ===")
    d1 = upload("gavrilov", "gavrilov")
    print(f"  новых: {len(d1.get('items', []))}, дублей: {d1.get('skipped_duplicates', 0)}")

    # Подтверждаем добавление (как делает фронтенд)
    r = httpx.post(f"{BASE}/api/auth/login", json={"username": "gavrilov", "password": "gavrilov"})
    H = {"Authorization": f"Bearer {r.json()['access_token']}", "Content-Type": "application/json"}
    r = httpx.post(f"{BASE}/api/schedule/batch", headers=H, json={"items": d1.get("items", [])}, timeout=60)
    print(f"  /schedule/batch → {r.status_code}, добавлено записей: {len(r.json()) if r.status_code < 300 else r.text[:200]}")

    sched1 = httpx.get(f"{BASE}/api/schedule/my", headers=H).json()
    print(f"  в календаре: {len(sched1)}")

    print("\n=== Импорт 2 (тот же файл повторно) ===")
    d2 = upload("gavrilov", "gavrilov")
    print(f"  новых: {len(d2.get('items', []))}, дублей: {d2.get('skipped_duplicates', 0)}")
    r = httpx.post(f"{BASE}/api/schedule/batch", headers=H, json={"items": d2.get("items", [])}, timeout=60)
    print(f"  /schedule/batch → {r.status_code}, добавлено: {len(r.json()) if r.status_code < 300 else '—'}")

    sched2 = httpx.get(f"{BASE}/api/schedule/my", headers=H).json()
    print(f"  в календаре: {len(sched2)}")

    print("\n=== ИТОГ ===")
    print(f"После 1-го импорта: {len(sched1)}")
    print(f"После 2-го импорта: {len(sched2)}")
    if len(sched2) == len(sched1):
        print("✅ Повторный импорт не создал дублей")
    else:
        print(f"❌ Добавилось {len(sched2) - len(sched1)} дублей")

    keys = set(); dups = 0
    for s in sched2:
        k = (s['title'].lower(), s['day_of_week'], s['start_time'], s['group_name'].lower())
        if k in keys: dups += 1
        keys.add(k)
    print(f"Дублей в календаре: {dups}")


asyncio.run(main())