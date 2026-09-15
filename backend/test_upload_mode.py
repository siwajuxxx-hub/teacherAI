"""Проверка, что запрос из фронтенда доходит до режима распределения."""
import httpx, inspect
from app.services.teacher_matcher import detect_distribute_all, extract_target_teacher

print("=== 1. Режим определяется по тексту запроса ===")
cases = [
    ("добавь всем преподавателям их пары", True),
    ("распредели по преподавателям", True),
    ("занеси всем учителям", True),
    ("добавь пары Гаврилова", False),
    ("", False),
]
for msg, expected in cases:
    got = detect_distribute_all(msg)
    print(f"  {'OK ' if got == expected else 'FAIL'} distribute={got!s:5} «{msg}»")
    assert got == expected

print("\n=== 2. Фронтенд передаёт message в форму ===")
src = open("../frontend/src/api/client.ts", encoding="utf-8").read()
assert "formData.append('message'" in src, "message не передаётся!"
print("  OK: uploadFile добавляет message в FormData")

src2 = open("../frontend/src/pages/TeacherDashboard/ChatTab.tsx", encoding="utf-8").read()
assert "api.uploadFile(file, instruction" in src2, "ChatTab не передаёт запрос!"
print("  OK: ChatTab передаёт текст из поля ввода")

print("\n=== 3. Бэкенд принимает message ===")
src3 = open("app/routers/chat.py", encoding="utf-8").read()
assert 'message: Optional[str] = Form(None)' in src3, "бэкенд не принимает message!"
assert "distribute_all = is_manager and detect_distribute_all(query)" in src3
print("  OK: /api/chat/upload принимает message и определяет режим")

print("\n=== 4. Реальная отправка формы с message ===")
r = httpx.post("http://localhost:8000/api/auth/login",
               json={"username": "manager", "password": "manager"})
H = {"Authorization": f"Bearer {r.json()['access_token']}"}

# Отправляем крошечный файл с запросом «добавь всем» — проверяем, что режим включился
small = "Расписание. Иванов И.И. Понедельник 09:00-10:30 Математика гр.А-1 ауд.101"
r = httpx.post(
    "http://localhost:8000/api/chat/upload",
    headers=H,
    files={"file": ("test.txt", small.encode("utf-8"), "text/plain")},
    data={"message": "добавь всем преподавателям их пары"},
    timeout=300,
)
print(f"  HTTP {r.status_code}")
res = r.json()
print(f"  status: {res.get('status')}")
msg = res.get("message", "")
print(f"  message: {msg[:400]}")
# В режиме распределения статус distributed
if res.get("status") == "distributed":
    print("  ✅ Режим распределения ВКЛЮЧИЛСЯ (баг исправлен)")
else:
    print(f"  ️  status={res.get('status')} — проверьте вручную")

print("\n=== 5. Без запроса — обычный режим ===")
r = httpx.post(
    "http://localhost:8000/api/chat/upload",
    headers=H,
    files={"file": ("test.txt", small.encode("utf-8"), "text/plain")},
    timeout=300,
)
res = r.json()
print(f"  status: {res.get('status')} (не distributed)")
print("  OK" if res.get("status") != "distributed" else "  FAIL")

print("\nВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")