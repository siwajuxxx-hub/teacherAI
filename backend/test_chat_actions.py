"""Тест логики действий чата: разбор и выполнение."""
import asyncio
from app.database import init_databases
from app.services.chat_actions import extract_actions, execute_actions
from app.models.auth_models import User


def test_extract():
    ai_text = """Понял, переношу пару на среду.

```actions
[{"action":"update_schedule","params":{"title":"Математика","day_of_week":2,"room":"401"}},
 {"action":"create_task","params":{"title":"Проверить тетради","due_date":"2026-09-18","priority":"high"}}]
```"""
    actions, clean = extract_actions(ai_text)
    print("Извлечено действий:", len(actions))
    for a in actions:
        print("  -", a["description"])
    print("Текст без блока:", repr(clean))
    assert len(actions) == 2, "Должно быть 2 действия"
    assert "actions" not in clean, "Блок должен быть удалён из текста"
    print("OK extract\n")


def test_extract_none():
    text = "Сегодня у вас 3 пары: математика, физика, информатика."
    actions, clean = extract_actions(text)
    assert actions == [], "Не должно быть действий"
    assert clean == text, "Текст не должен меняться"
    print("OK no-actions\n")


async def main():
    await init_databases()
    test_extract()
    test_extract_none()

    # Реальное выполнение под преподавателем
    from app.database import AuthSessionLocal
    from sqlalchemy import select
    async with AuthSessionLocal() as s:
        r = await s.execute(select(User).where(User.username == "teacher"))
        teacher = r.scalar_one()

    print("=== Выполнение действий ===")

    # 1. Создать задачу
    res = await execute_actions(teacher, [
        {"action": "create_task", "params": {"title": "Тестовая задача из чата", "priority": "high", "due_date": "2026-09-20"}}
    ])
    for r in res:
        print(f"  {'OK ' if r['ok'] else 'FAIL'} {r['message']}")
    assert res[0]["ok"], res[0]["message"]

    # 2. Сменить статус
    res = await execute_actions(teacher, [
        {"action": "update_task_status", "params": {"title": "Тестовая задача из чата", "status": "done"}}
    ])
    for r in res:
        print(f"  {'OK ' if r['ok'] else 'FAIL'} {r['message']}")
    assert res[0]["ok"], res[0]["message"]

    # 3. Добавить пару
    res = await execute_actions(teacher, [
        {"action": "create_schedule", "params": {"title": "Тестовая пара из чата", "day_of_week": 2, "start_time": "14:00", "end_time": "15:30", "room": "401", "group_name": "ТЕСТ-1"}}
    ])
    for r in res:
        print(f"  {'OK ' if r['ok'] else 'FAIL'} {r['message']}")
    assert res[0]["ok"], res[0]["message"]

    # 4. Перенести пару (сменить день и аудиторию)
    res = await execute_actions(teacher, [
        {"action": "update_schedule", "params": {"title": "Тестовая пара из чата", "day_of_week": 4, "room": "529"}}
    ])
    for r in res:
        print(f"  {'OK ' if r['ok'] else 'FAIL'} {r['message']}")
    assert res[0]["ok"], res[0]["message"]

    # 5. Удалить (только преподаватель не может удалять MANAGER-записи — эта MANUAL, ок)
    res = await execute_actions(teacher, [
        {"action": "delete_schedule", "params": {"title": "Тестовая пара из чата"}}
    ])
    for r in res:
        print(f"  {'OK ' if r['ok'] else 'FAIL'} {r['message']}")
    assert res[0]["ok"], res[0]["message"]

    # 6. Удалить задачу
    res = await execute_actions(teacher, [
        {"action": "delete_task", "params": {"title": "Тестовая задача из чата"}}
    ])
    for r in res:
        print(f"  {'OK ' if r['ok'] else 'FAIL'} {r['message']}")
    assert res[0]["ok"], res[0]["message"]

    # 7. Несуществующая запись — понятная ошибка
    res = await execute_actions(teacher, [
        {"action": "delete_task", "params": {"title": "Такой задачи нет 12345"}}
    ])
    print(f"  {'OK ' if not res[0]['ok'] else 'FAIL'} {res[0]['message']}")
    assert not res[0]["ok"]

    print("\nВСЕ ТЕСТЫ ПРОЙДЕНЫ")


asyncio.run(main())