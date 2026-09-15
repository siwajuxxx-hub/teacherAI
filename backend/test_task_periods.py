"""Тесты периодов задач и страховки от потери задач из чата."""
import asyncio
from datetime import date, timedelta
from app.database import init_databases, DataSessionLocal, AuthSessionLocal
from app.models.auth_models import User
from app.models.data_models import Task
from app.services.chat_actions import (
    extract_actions, execute_actions, salvage_action, _resolve_period, _extract_task_params,
)
from sqlalchemy import select, delete


def test_salvage():
    print("=== Страховка: разбор текста пользователя ===")
    cases = [
        ("Добавь задачу сдать отчёт на 25 сентября", "day"),
        ("добавь задачу проверить журналы в октябре", "month"),
        ("поставь задачу подготовить курс на 2026 год", "year"),
        ("напомни купить мел", "none"),
        ("Добавь задачу позвонить завтра", "day"),
        ("создай задачу отчёт на 15.10.2026", "day"),
        ("поставь задачу на пятницу проверить тетради", "day"),
        ("добавь заметку прочитать статью", "none"),
    ]
    ok = 0
    for text, expected_scope in cases:
        a = salvage_action(text)
        if not a:
            print(f"  ❌ НЕ РАСПОЗНАНО: {text}")
            continue
        p = a["params"]
        if "due_date" in p:
            scope = "day"
        elif "due_month" in p:
            scope = "month"
        elif "due_year" in p:
            scope = "year"
        else:
            scope = "none"
        mark = "OK " if scope == expected_scope else "?? "
        if scope == expected_scope:
            ok += 1
        print(f"  {mark} «{text}»\n      -> title={p.get('title')!r} {scope}={p.get('due_date') or p.get('due_month') or p.get('due_year') or '—'}")

    print(f"\nРаспознано верно: {ok}/{len(cases)}")

    print("\n=== Не должно срабатывать (обычные вопросы) ===")
    for text in ["какие сегодня у меня пары?", "сколько задач я выполнил?", "перенеси пару на среду"]:
        a = salvage_action(text)
        print(f"  {'❌ ЛОЖНОЕ СРАБАТЫВАНИЕ' if a else 'OK '} «{text}» -> {a}")
        assert a is None, f"Ложное срабатывание на: {text}"

    print("\n=== extract_actions со страховкой ===")
    # AI не вернул блок actions
    ai_text = "Хорошо, я добавил задачу."
    acts, clean = extract_actions(ai_text, user_message="добавь задачу сдать отчёт на 25 сентября")
    print(f"  AI без блока -> действий: {len(acts)}")
    for a in acts:
        print(f"    {a['description']} | params={a['params']}")
    assert acts, "Задача потерялась!"

    # AI вернул блок — страховка не должна дублировать
    ai_text2 = 'Добавляю.\n\n```actions\n[{"action":"create_task","params":{"title":"Сдать отчёт","due_date":"2026-09-25"}}]\n```'
    acts2, _ = extract_actions(ai_text2, user_message="добавь задачу сдать отчёт на 25 сентября")
    print(f"  AI с блоком -> действий: {len(acts2)} (ожидается 1, без дубля)")
    assert len(acts2) == 1

    print("\nOK страховка работает\n")


async def test_execute():
    await init_databases()
    async with AuthSessionLocal() as s:
        r = await s.execute(select(User).where(User.username == "teacher"))
        teacher = r.scalar_one()

    async with DataSessionLocal() as db:
        await db.execute(delete(Task).where(Task.user_id == teacher.id))
        await db.commit()

    print("=== Создание задач с разными периодами ===")
    res = await execute_actions(teacher, [
        {"action": "create_task", "params": {"title": "Дневная задача", "due_date": "2026-09-25"}},
        {"action": "create_task", "params": {"title": "Месячная задача", "due_month": "2026-10"}},
        {"action": "create_task", "params": {"title": "Годовая задача", "due_year": 2026}},
        {"action": "create_task", "params": {"title": "Без срока"}},
        {"action": "create_task", "params": {"title": "Текстом месяц", "period": "в ноябре"}},
    ])
    for r in res:
        print(f"  {'OK ' if r['ok'] else 'FAIL'} {r['message']}")
        assert r["ok"], r["message"]

    async with DataSessionLocal() as db:
        r = await db.execute(select(Task).where(Task.user_id == teacher.id))
        for t in r.scalars().all():
            print(f"    «{t.title}» scope={t.scope.value} date={t.due_date} month={t.due_month} year={t.due_year}")
        assert (await db.execute(select(Task).where(Task.user_id == teacher.id))).scalars().all().__len__() == 5

    print("\n=== Смена периода у задачи ===")
    res = await execute_actions(teacher, [
        {"action": "update_task", "params": {"title": "Дневная задача", "due_month": "2026-12"}},
    ])
    for r in res:
        print(f"  {'OK ' if r['ok'] else 'FAIL'} {r['message']}")
        assert r["ok"]

    async with DataSessionLocal() as db:
        r = await db.execute(select(Task).where(Task.user_id == teacher.id, Task.title == "Дневная задача"))
        t = r.scalar_one()
        print(f"    после смены: scope={t.scope.value} month={t.due_month} date={t.due_date}")
        assert t.scope.value == "month" and t.due_month == "2026-12" and t.due_date is None

    print("\n=== Дата завершения фиксируется ===")
    await execute_actions(teacher, [
        {"action": "update_task_status", "params": {"title": "Без срока", "status": "done"}},
    ])
    async with DataSessionLocal() as db:
        r = await db.execute(select(Task).where(Task.user_id == teacher.id, Task.title == "Без срока"))
        t = r.scalar_one()
        print(f"    статус={t.status.value} completed_at={t.completed_at}")
        assert t.completed_at is not None

    # Уборка
    async with DataSessionLocal() as db:
        await db.execute(delete(Task).where(Task.user_id == teacher.id))
        await db.commit()

    print("\nВСЕ ТЕСТЫ ПЕРИОДОВ ПРОЙДЕНЫ")


test_salvage()
asyncio.run(test_execute())