"""Действия из AI-чата: разбор предложений AI и их выполнение.

Схема работы (двухфазная, безопасная):
1. AI в конце ответа возвращает блок ```actions [...] ``` с JSON-командами.
2. `/send` извлекает команды и ОТПРАВЛЯЕТ их клиенту как предложения (не выполняет).
3. Пользователь подтверждает → клиент зовёт `/execute-actions` → здесь выполняется.

Так ничего не удаляется/не меняется без явного согласия пользователя.
"""

import json
import re
from datetime import date, time, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import DataSessionLocal
from app.models.data_models import (
    Schedule, Task, ScheduleType, ScheduleSource, TaskStatus, TaskScope,
)

# ─── Описание действий для системного промпта ─────────────────────

TOOL_PROMPT = """
## Управление календарём и заметками через чат

Ты умеешь предлагать действия с расписанием (календарь) и задачами (заметки).
Если пользователь просит что-то создать, изменить, перенести, удалить или сменить статус —
ОБЯЗАТЕЛЬНО добавь в САМЫЙ КОНЕЦ ответа блок с командами в формате:

```actions
[
  {"action": "имя_действия", "params": { ... }}
]
```

Действия НЕ выполняются сразу — их подтверждает пользователь, поэтому смело предлагай их.

### Доступные действия

### Задачи (заметки)

ВАЖНО: у задач НЕТ приоритета. У задачи есть только СРОК, и он бывает трёх видов:

| Вид срока | Поля в params | Пример запроса пользователя |
|---|---|---|
| Конкретный день | due_date: "YYYY-MM-DD" | «на 25 сентября», «завтра», «в пятницу» |
| Месяц | due_month: "YYYY-MM" | «в сентябре», «на сентябрь», «в течение месяца» |
| Год | due_year: 2026 | «в 2026 году», «на этот год» |
| Без срока | ничего не указывать | «добавь заметку купить мел» |

Если пользователь называет месяц словами («в октябре») — вычисли год сам (текущий или следующий,
если месяц уже прошёл) и передай due_month в формате "YYYY-MM".
Если называет только год — due_year. Если конкретный день — due_date.

- create_task — создать задачу
  params: {"title": "Название", "description": ""}  + один из: due_date / due_month / due_year
  Примеры:
    «напомни сдать отчёт 25 сентября»     → {"title":"Сдать отчёт","due_date":"2026-09-25"}
    «проверить журналы в октябре»        → {"title":"Проверить журналы","due_month":"2026-10"}
    «подготовить отчёт за октябрь»       → {"title":"Подготовить отчёт","due_month":"2026-10"}
    «подготовить курс на 2026 год»       → {"title":"Подготовить курс","due_year":2026}
    «сделать до конца месяца»            → {"title":"Сделать","due_month":"2026-09"}
    «купить мел» (без срока)             → {"title":"Купить мел"}

  ВАЖНО про title: пиши только суть дела, БЕЗ указания срока.
    ✓ «Проверить журналы»   ✗ «Проверить журналы в октябре»
  Срок всегда идёт в due_date / due_month / due_year, а не в название.

- update_task — изменить задачу (название, описание, срок любого вида)
  params: {"title": "как найти задачу", "new_title": "...", "due_date": "...", "due_month": "...", "due_year": ...}
- update_task_status — сменить статус
  params: {"title": "как найти задачу", "status": "pending|in_progress|done"}
- delete_task — удалить задачу
  params: {"title": "как найти задачу"}

Расписание (календарь):
- create_schedule — добавить пару
  params: {"title": "Название", "day_of_week": 0, "date": "YYYY-MM-DD или НЕ указывать",
           "start_time": "09:00", "end_time": "10:30",
           "group_name": "ЭС1-24з", "room": "529", "type": "lesson|meeting|other"}
  «завтра/25 сентября/в конкретный день» → ОБЯЗАТЕЛЬНО date (+день подставится сам).
  Регулярная пара без даты («по пятницам») → только day_of_week, date не указывай.
  Ты НЕ УКАЗЫВАЕШЬ чужого владельца: если управляющий просит «поставь преподавателю X
  пару» — добавь "teacher_name": "X" (система сама найдёт владельца).
- update_schedule — изменить пару: перенести на другой день/дату/время, сменить аудиторию,
  группу, название, а также ПРЕПОДАВАТЕЛЯ-ВЛАДЕЛЬЦА (только управляющий/админ)
  params: {"title": "как найти пару", "date": "YYYY-MM-DD", "day_of_week": 3,
           "start_time": "12:00", "end_time": "13:30",
           "room": "401", "group_name": "ЭО1-24з", "new_title": "Новое название",
           "teacher_name": "Фамилия И.О.", "target_teacher_name": "Фамилия И.О."}
  — указывай ТОЛЬКО те поля, которые надо изменить;
  — teacher_name — ЧЬЮ пару править (нужно управляющему, когда говорит про другого);
  — target_teacher_name — НА КОГО перенести пару (только управляющий/админ).
- delete_schedule — удалить пару
  params: {"title": "как найти пару", "date": "YYYY-MM-DD", "day_of_week": 3,
           "teacher_name": "Фамилия И.О." (для управляющего — чью)}

### Правила
1. day_of_week: 0=Понедельник, 1=Вторник, 2=Среда, 3=Четверг, 4=Пятница, 5=Суббота, 6=Воскресенье.
2. Даты считай от сегодняшней (она указана выше). «Завтра», «в пятницу» — вычисли конкретную дату YYYY-MM-DD.
3. В поле "title" для update/delete — указывай узнаваемую часть названия, как оно есть в списках выше.
4. Перед блоком ```actions обязательно напиши короткое пояснение человеческим языком.
5. Если действие не требуется (просто вопрос) — блок actions НЕ добавляй.
6. Никогда не выдумывай записи: опирайся только на списки расписания и задач выше.
7. Содержимого файлов ты не видишь — в контексте бывает только сводка последнего
   импорта (кто и сколько пар). Команды «добавь пары X ко мне», «перенеси в её
   календарь», «распредели всем» система исполняет сама из сохранённого импорта —
   отвечай на них словами, НЕ создавай create_schedule по памяти.
   create_schedule допустим только для одиночной пары, где пользователь сам назвал
   день недели/дату и/или время («в пятницу на 12:00», «завтра в 14:00»).
8. Очистку календаря («очисти всё», «удали все пары в среду») система делает сама
   через карточку подтверждения — действий delete_schedule «на всё» НЕ создавай,
   удаляй точечно только явно названные предметы.

### Пример
Пользователь: «Перенеси пару по математике с понедельника на среду в 401 аудиторию»
Ответ: Перенесу пару «Математика» на среду, аудитория 401.

```actions
[{"action":"update_schedule","params":{"title":"Математика","day_of_week":2,"room":"401"}}]
```

Пользователь (управляющий): «Поставь Гаврилову собрание в пятницу 25 сентября в 14:00»
Ответ: Предлагаю добавить Гаврилову собрание в пятницу 25.09 в 14:00.

```actions
[{"action":"create_schedule","params":{"title":"Собрание","date":"2026-09-25","start_time":"14:00","end_time":"15:30","type":"meeting","teacher_name":"Гаврилову"}}]
```
"""


# ─── Разбор действий из ответа AI ────────────────────────────────

def extract_actions(text: str, user_message: str = "") -> tuple[list[dict], str]:
    """Извлекает действия из ответа AI.

    Возвращает (список действий, текст без блока с действиями).
    user_message — исходный запрос пользователя, нужен для страховки.
    """
    actions: list[dict] = []
    cleaned = text

    pattern = re.compile(r"```actions\s*\n?(.*?)```", re.DOTALL)
    matches = list(pattern.finditer(text))

    if not matches:
        # fallback: блок ```json с ключом action
        pattern = re.compile(r"```json\s*\n?(.*?)```", re.DOTALL)
        matches = [m for m in pattern.finditer(text) if '"action"' in m.group(1)]

    for m in matches:
        try:
            data = json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            data = [data]
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("action"):
                    actions.append(item)

    # Убираем блоки действий из отображаемого текста
    if matches:
        cleaned = re.sub(r"```(?:actions|json)\s*\n?.*?```", "", text, flags=re.DOTALL)
        cleaned = cleaned.strip()

    # Валидируем и добавляем человекочитаемое описание
    valid = []
    for a in actions:
        desc = describe_action(a)
        if desc:
            a = dict(a)
            a["description"] = desc
            valid.append(a)

    # ── Страховка: AI не вернул блок, но пользователь явно просил задачу ──
    if not valid and user_message:
        fallback = salvage_action(user_message)
        if fallback:
            valid.append(fallback)

    return valid, cleaned


# ─── Страховка от потери задач ───────────────────────────────────
#
# Модель не всегда добавляет блок ```actions (особенно на коротких запросах).
# Чтобы задача не потерялась, разбираем намерение из текста пользователя.

_CREATE_TASK_RE = re.compile(
    r"(добав|созда|постав|запиш|напомн|внеси|нужн|надо)[^\n]{0,60}?"
    r"(задач\w*|заметк\w*|напомин\w*)",
    re.IGNORECASE,
)

# «напомни купить мел» — глагол-напоминание без слова «задача»
_REMIND_RE = re.compile(
    r"^\s*(пожалуйста[,\s]*)?(напомни|напомнить|не\s+забудь|не\s+забыть)\b",
    re.IGNORECASE,
)

_MONTH_STEMS = [
    ("январ", 1), ("феврал", 2), ("март", 3), ("апрел", 4), ("май", 5), ("ма", 5),
    ("июн", 6), ("июл", 7), ("август", 8), ("сентябр", 9), ("октябр", 10),
    ("ноябр", 11), ("декабр", 12),
]


def salvage_action(user_message: str) -> dict | None:
    """Пытается восстановить намерение создать задачу из текста пользователя.

    Вызывается только если AI не вернул ни одной команды. Это гарантия,
    что задача, поставленная через чат, не потеряется.
    """
    if not user_message:
        return None

    low = user_message.lower()

    # Явное создание задачи/заметки ИЛИ просьба напомнить
    if not (_CREATE_TASK_RE.search(low) or _REMIND_RE.search(low)):
        return None

    params = _extract_task_params(user_message)
    if not params.get("title"):
        return None

    action = {"action": "create_task", "params": params}
    action["description"] = describe_action(action)
    return action


def _extract_task_params(text: str) -> dict:
    """Извлекает заголовок, описание и срок из свободного текста."""
    params: dict = {}

    # ── Заголовок ──
    title = text
    # Убираем вводные слова (включая «напомни»)
    title = re.sub(
        r"^\s*(пожалуйста[,\s]*)?(добавь|создай|поставь|запиши|напомни|напомнить|внеси|"
        r"нужно|надо|не\s+забудь)\s*"
        r"(мне\s*)?(новую\s*)?(задачу|заметку|напоминание)?\s*[:\-—]?\s*",
        "", title, flags=re.IGNORECASE,
    )

    # Убираем указание срока из заголовка: «на 25 сентября», «в октябре», «на 2026 год»,
    # «завтра», «на пятницу», «15.10.2026»
    period_patterns = [
        r"\b(на|в|до|к|с)\s+\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?\b",
        r"\b\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?\b",
        r"\b(на|в|до|к|с)\s+\d{1,2}\s+"
        r"(январ\w*|феврал\w*|март\w*|апрел\w*|ма[йея]\w*|июн\w*|июл\w*|август\w*|"
        r"сентябр\w*|октябр\w*|ноябр\w*|декабр\w*)",
        r"\b\d{1,2}\s+"
        r"(январ\w*|феврал\w*|март\w*|апрел\w*|ма[йея]\w*|июн\w*|июл\w*|август\w*|"
        r"сентябр\w*|октябр\w*|ноябр\w*|декабр\w*)",
        r"\b(на|в|до|к|с)\s+(20\d{2})\s*(год\w*|г\.?)?\b",
        r"\b(на|в|до|к|с)\s+"
        r"(январ\w*|феврал\w*|март\w*|апрел\w*|ма[йея]\w*|июн\w*|июл\w*|август\w*|"
        r"сентябр\w*|октябр\w*|ноябр\w*|декабр\w*)",
        r"\b(завтра|сегодня|послезавтра)\b",
        r"\b(на|в|к|до)\s+"
        r"(понедельник\w*|вторник\w*|сред\w*|четверг\w*|пятниц\w*|суббот\w*|воскресень\w*)",
        r"\b(в\s+)?(этом|текущем|следующем)\s+(месяце|году)",
        r"\bна\s+(этот\s+)?год\b",
        r"\bза\s+"
        r"(январ\w*|феврал\w*|март\w*|апрел\w*|ма[йея]\w*|июн\w*|июл\w*|август\w*|"
        r"сентябр\w*|октябр\w*|ноябр\w*|декабр\w*)",
        r"\bза\s+(20\d{2})\s*(год\w*)?",
    ]
    for pat in period_patterns:
        title = re.sub(pat, " ", title, flags=re.IGNORECASE)

    title = re.sub(r"\s{2,}", " ", title).strip(" .,;:-—")
    if len(title) > 200:
        title = title[:200].rstrip() + "…"
    if title:
        params["title"] = title

    # ── Срок ──
    low = text.lower()
    today = date.today()

    # Конкретная дата: 25.09.2026 / 25.09 / 2026-09-25
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
    if m:
        params["due_date"] = m.group(0)
        return params

    m = re.search(r"\b(\d{1,2})[.](\d{1,2})(?:[.](\d{2,4}))?\b", text)
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        y = int(m.group(3)) if m.group(3) else today.year
        if y < 100:
            y += 2000
        try:
            params["due_date"] = date(y, mo, d).isoformat()
            return params
        except ValueError:
            pass

    # Относительные дни
    if "послезавтра" in low:
        params["due_date"] = (today + timedelta(days=2)).isoformat()
        return params
    if "завтра" in low:
        params["due_date"] = (today + timedelta(days=1)).isoformat()
        return params
    if "сегодня" in low:
        params["due_date"] = today.isoformat()
        return params

    # День недели
    weekdays = {
        "понедельник": 0, "вторник": 1, "сред": 2, "четверг": 3,
        "пятниц": 4, "суббот": 5, "воскресен": 6,
    }
    for stem, wd in weekdays.items():
        if stem in low:
            ahead = (wd - today.weekday()) % 7
            if ahead == 0:
                ahead = 7
            params["due_date"] = (today + timedelta(days=ahead)).isoformat()
            return params

    # Число + месяц словами: «25 сентября», «3 октября 2026» — конкретный день
    m = re.search(
        r"\b(\d{1,2})\s+"
        r"(январ\w*|феврал\w*|март\w*|апрел\w*|ма[йея]\w*|июн\w*|июл\w*|август\w*|"
        r"сентябр\w*|октябр\w*|ноябр\w*|декабр\w*)"
        r"(?:\s+(20\d{2}))?",
        low,
    )
    if m:
        day_num = int(m.group(1))
        month_num = next((num for stem, num in _MONTH_STEMS if stem in m.group(2)), None)
        year_num = int(m.group(3)) if m.group(3) else today.year
        if month_num:
            try:
                candidate = date(year_num, month_num, day_num)
                # Если дата уже прошла и год не указан — берём следующий год
                if not m.group(3) and candidate < today:
                    candidate = date(year_num + 1, month_num, day_num)
                params["due_date"] = candidate.isoformat()
                return params
            except ValueError:
                pass

    # Год (только 4 цифры со словом «год»)
    m = re.search(r"\b(20\d{2})\s*(?:год|году|г\.)", low)
    if m:
        params["due_year"] = int(m.group(1))
        return params

    # Месяц
    year_match = re.search(r"\b(20\d{2})\b", text)
    found_year = int(year_match.group(1)) if year_match else None
    for stem, num in _MONTH_STEMS:
        if stem in low:
            y = found_year or today.year
            # Если месяц уже прошёл в этом году — переносим на следующий
            if not found_year and num < today.month:
                y += 1
            params["due_month"] = f"{y:04d}-{num:02d}"
            return params

    # «за октябрь» / «в течение месяца» без названия месяца
    if re.search(r"\bза\s+месяц\b", low) or re.search(r"\bв\s+течение\s+месяца\b", low):
        params["due_month"] = f"{today.year:04d}-{today.month:02d}"
        return params

    # Просто «в этом году» / «на год»
    if re.search(r"\b(на\s+)?(этот|текущий|следующий)\s+год", low) or "на год" in low:
        y = today.year + (1 if "следующ" in low else 0)
        params["due_year"] = y
        return params

    # «в этом месяце»
    if "месяц" in low:
        params["due_month"] = f"{today.year:04d}-{today.month:02d}"

    return params


# ─── Человекочитаемое описание ───────────────────────────────────

DAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

_STATUS_RU = {
    "pending": "к выполнению",
    "in_progress": "в работе",
    "done": "выполнено",
    "overdue": "просрочено",
}

_PRIORITY_RU = {"low": "низкий", "medium": "средний", "high": "высокий"}


def _describe_period(p: dict) -> str:
    """Человекочитаемое описание периода задачи для карточки подтверждения."""
    if p.get("due_date"):
        d = _parse_date(p["due_date"])
        return f", срок {d.strftime('%d.%m.%Y')}" if d else f", срок {p['due_date']}"
    if p.get("due_month"):
        m = _parse_month(p["due_month"])
        return f", на месяц {_month_ru(m)}" if m else f", месяц {p['due_month']}"
    if p.get("due_year"):
        return f", на {p['due_year']} год"
    if p.get("period"):
        return f", период {p['period']}"
    return ""


def describe_action(a: dict) -> str:
    """Строит короткое описание действия для интерфейса."""
    act = a.get("action", "")
    p = a.get("params", {}) or {}
    title = p.get("title") or p.get("new_title") or "?"

    if act == "create_task":
        return f"Создать задачу «{title}»{_describe_period(p)}"

    if act == "update_task":
        parts = []
        if p.get("new_title"):
            parts.append(f"название → «{p['new_title']}»")
        if p.get("description"):
            parts.append("описание")
        period = _describe_period(p)
        if period:
            parts.append(f"срок{period}")
        return f"Изменить задачу «{title}»" + (f": {', '.join(parts)}" if parts else "")

    if act == "update_task_status":
        st = _STATUS_RU.get(str(p.get("status", "")).lower(), p.get("status", "?"))
        return f"Сменить статус задачи «{title}» → «{st}»"

    if act == "delete_task":
        return f"Удалить задачу «{title}»"

    if act == "create_schedule":
        d = p.get("day_of_week")
        day = DAYS[d] if isinstance(d, int) and 0 <= d < 7 else "?"
        if p.get("date"):
            try:
                dt = date.fromisoformat(str(p["date"])[:10])
                day = f"{dt.strftime('%d.%m.%Y')} ({day})"
            except ValueError:
                pass
        tm = ""
        if p.get("start_time"):
            tm = f" {p['start_time']}"
            if p.get("end_time"):
                tm += f"–{p['end_time']}"
        extra = []
        if p.get("room"):
            extra.append(f"ауд. {p['room']}")
        if p.get("group_name"):
            extra.append(f"гр. {p['group_name']}")
        tail = f" ({', '.join(extra)})" if extra else ""
        return f"Добавить пару «{title}»: {day}{tm}{tail}"

    if act == "update_schedule":
        parts = []
        if isinstance(p.get("day_of_week"), int):
            parts.append(f"день → {DAYS[p['day_of_week']]}")
        if p.get("start_time"):
            parts.append(f"начало → {p['start_time']}")
        if p.get("end_time"):
            parts.append(f"конец → {p['end_time']}")
        if p.get("room"):
            parts.append(f"аудитория → {p['room']}")
        if p.get("group_name"):
            parts.append(f"группа → {p['group_name']}")
        if p.get("new_title"):
            parts.append(f"название → «{p['new_title']}»")
        if p.get("teacher_name"):
            parts.append(f"преподаватель → {p['teacher_name']}")
        return f"Изменить пару «{title}»" + (f": {', '.join(parts)}" if parts else "")

    if act == "delete_schedule":
        return f"Удалить пару «{title}»"

    return ""


# ─── Выполнение действий ─────────────────────────────────────────

async def execute_actions(user, actions: list[dict]) -> list[dict]:
    """Выполняет подтверждённые действия. Возвращает список результатов."""
    results = []

    for a in actions:
        act = a.get("action", "")
        params = a.get("params", {}) or {}

        try:
            async with DataSessionLocal() as db:
                ok, message = await _dispatch(db, user, act, params)
                if ok:
                    await db.commit()
                else:
                    await db.rollback()
        except Exception as e:
            ok, message = False, f"Ошибка выполнения: {e}"

        results.append({"action": act, "ok": ok, "message": message})

    return results


async def _dispatch(db: AsyncSession, user, act: str, p: dict) -> tuple[bool, str]:
    handlers = {
        "create_task": _create_task,
        "update_task": _update_task,
        "update_task_status": _update_task_status,
        "delete_task": _delete_task,
        "create_schedule": _create_schedule,
        "update_schedule": _update_schedule,
        "delete_schedule": _delete_schedule,
    }
    handler = handlers.get(act)
    if not handler:
        return False, f"Неизвестное действие: {act}"
    return await handler(db, user, p)


# ── Права доступа ────────────────────────────────────────────────

def _can_touch(user, owner_id: str) -> bool:
    """Преподаватель — только свои записи; управляющий/админ — любые."""
    if user.role in ("admin", "manager"):
        return True
    return user.id == owner_id


# ── Задачи ───────────────────────────────────────────────────────

async def _create_task(db, user, p: dict) -> tuple[bool, str]:
    title = (p.get("title") or "").strip()
    if not title:
        return False, "Не указано название задачи"

    scope, due_date, due_month, due_year, label = _resolve_period(p)
    if scope == "error":
        return False, label

    task = Task(
        user_id=p.get("_owner_id") or user.id,
        title=title,
        description=p.get("description", "") or "",
        status=TaskStatus.PENDING,
        scope=scope,
        due_date=due_date,
        due_month=due_month,
        due_year=due_year,
        assigned_by=None if (p.get("_owner_id") or user.id) == user.id else user.id,
    )
    db.add(task)
    await db.flush()
    return True, f"Задача «{title}» создана в заметках{label}"


async def _update_task(db, user, p: dict) -> tuple[bool, str]:
    task = await _find_task(db, user, p.get("id") or p.get("title") or "")
    if not task:
        return False, f"Задача «{p.get('title')}» не найдена"
    if not _can_touch(user, task.user_id):
        return False, "Нет прав на изменение этой задачи"

    changed = []
    if p.get("new_title"):
        task.title = p["new_title"]
        changed.append("название")
    if p.get("description"):
        task.description = p["description"]
        changed.append("описание")

    # Смена периода
    period_keys = ("scope", "due_date", "due_month", "due_year", "period")
    if any(k in p for k in period_keys):
        scope, due_date, due_month, due_year, label = _resolve_period(p)
        if scope == "error":
            return False, label
        task.scope = scope
        task.due_date = due_date
        task.due_month = due_month
        task.due_year = due_year
        changed.append(f"срок{label}")

    if not changed:
        return False, "Не указано, что изменить"
    return True, f"Задача «{task.title}» обновлена ({', '.join(changed)})"


async def _update_task_status(db, user, p: dict) -> tuple[bool, str]:
    task = await _find_task(db, user, p.get("id") or p.get("title") or "")
    if not task:
        return False, f"Задача «{p.get('title')}» не найдена"
    if not _can_touch(user, task.user_id):
        return False, "Нет прав на изменение этой задачи"

    status = _parse_status(p.get("status", ""))
    if not status:
        return False, f"Неизвестный статус: {p.get('status')}"

    task.status = status
    if status == TaskStatus.DONE:
        task.completed_at = task.completed_at or datetime.utcnow()
    else:
        task.completed_at = None

    return True, f"Статус задачи «{task.title}» → «{_STATUS_RU.get(status.value, status.value)}»"


async def _delete_task(db, user, p: dict) -> tuple[bool, str]:
    task = await _find_task(db, user, p.get("id") or p.get("title") or "")
    if not task:
        return False, f"Задача «{p.get('title')}» не найдена"
    if not _can_touch(user, task.user_id):
        return False, "Нет прав на удаление этой задачи"

    name = task.title
    await db.delete(task)
    return True, f"Задача «{name}» удалена"


# ── Расписание ───────────────────────────────────────────────────

async def _create_schedule(db, user, p: dict) -> tuple[bool, str]:
    title = (p.get("title") or "").strip()
    if not title:
        return False, "Не указано название пары"

    # Конкретная дата («завтра в 14:00») или недельный шаблон (только day_of_week)
    event_date = _parse_date(p.get("date"))
    if p.get("date") and not event_date:
        return False, "Неверный формат даты (ожидается YYYY-MM-DD)"

    day = p.get("day_of_week")
    if day is None and event_date:
        day = event_date.weekday()
    try:
        day = int(day if day is not None else 0)
    except (TypeError, ValueError):
        return False, "Неверный день недели"
    if not 0 <= day <= 6:
        return False, "День недели должен быть от 0 (Пн) до 6 (Вс)"

    try:
        start = _parse_time(p.get("start_time", "09:00"))
        end = _parse_time(p.get("end_time", "10:30"))
    except Exception:
        return False, "Неверный формат времени (ожидается HH:MM)"

    # Владелец: по умолчанию — подтвердивший; для менеджера grounding кладёт _owner_id
    owner_id = p.get("_owner_id") or user.id
    s = Schedule(
        user_id=owner_id,
        title=title,
        day_of_week=day,
        start_time=start,
        end_time=end,
        group_name=p.get("group_name", "") or "",
        room=p.get("room", "") or "",
        type=_parse_type(p.get("type", "lesson")),
        source=ScheduleSource.MANUAL if owner_id == user.id else ScheduleSource.MANAGER,
        created_by=user.id,
        event_date=event_date,
    )
    db.add(s)
    await db.flush()
    when = event_date.strftime("%d.%m") if event_date else DAYS[day]
    return True, f"Пара «{title}» добавлена ({when}, {start.strftime('%H:%M')})"


async def _update_schedule(db, user, p: dict) -> tuple[bool, str]:
    entry = await _find_schedule(db, user, p.get("id") or p.get("title") or "")
    if not entry:
        return False, f"Пара «{p.get('title')}» не найдена"

    if not _can_touch(user, entry.user_id):
        return False, "Нет прав на изменение этой пары"
    if user.role == "teacher" and entry.source == ScheduleSource.MANAGER:
        return False, "Нельзя изменить пару, добавленную управляющим"

    changed = []

    if p.get("new_title"):
        entry.title = p["new_title"]
        changed.append("название")

    # Перенос на конкретную дату («перенеси пару на 25 сентября»)
    if p.get("date"):
        new_date = _parse_date(p["date"])
        if not new_date:
            return False, "Неверный формат даты (ожидается YYYY-MM-DD)"
        entry.event_date = new_date
        if p.get("day_of_week") is None:
            entry.day_of_week = new_date.weekday()
        changed.append(f"дата → {new_date.strftime('%d.%m.%Y')}")

    if p.get("day_of_week") is not None:
        try:
            day = int(p["day_of_week"])
        except (TypeError, ValueError):
            return False, "Неверный день недели"
        if not 0 <= day <= 6:
            return False, "День недели должен быть от 0 до 6"
        entry.day_of_week = day
        changed.append(f"день → {DAYS[day]}")

    if p.get("start_time"):
        try:
            entry.start_time = _parse_time(p["start_time"])
            changed.append("начало")
        except Exception:
            return False, "Неверный формат времени начала"

    if p.get("end_time"):
        try:
            entry.end_time = _parse_time(p["end_time"])
            changed.append("конец")
        except Exception:
            return False, "Неверный формат времени конца"

    if p.get("room") is not None:
        entry.room = p["room"]
        changed.append(f"аудитория → {p['room'] or '—'}")

    if p.get("group_name") is not None:
        entry.group_name = p["group_name"]
        changed.append(f"группа → {p['group_name'] or '—'}")

    if p.get("type"):
        entry.type = _parse_type(p["type"])
        changed.append("тип")

    # Смена преподавателя — только управляющий/админ
    if p.get("teacher_name"):
        if user.role not in ("admin", "manager"):
            return False, "Только управляющий может передать пару другому преподавателю"
        from app.services.teacher_matcher import find_user_by_teacher_name
        target = await find_user_by_teacher_name(db, p["teacher_name"])
        if not target:
            return False, f"Преподаватель «{p['teacher_name']}» не найден в системе"
        entry.user_id = target.id
        changed.append(f"преподаватель → {target.full_name}")

    if not changed:
        return False, "Не указано, что изменить в паре"

    return True, f"Пара «{entry.title}» обновлена: {', '.join(changed)}"


async def _delete_schedule(db, user, p: dict) -> tuple[bool, str]:
    entry = await _find_schedule(db, user, p.get("id") or p.get("title") or "")
    if not entry:
        return False, f"Пара «{p.get('title')}» не найдена"

    if not _can_touch(user, entry.user_id):
        return False, "Нет прав на удаление этой пары"
    if user.role == "teacher" and entry.source == ScheduleSource.MANAGER:
        return False, "Нельзя удалить пару, добавленную управляющим"

    name = entry.title
    await db.delete(entry)
    return True, f"Пара «{name}» удалена из календаря"


# ── Поиск записей ────────────────────────────────────────────────

async def _find_task(db, user, needle: str) -> Task | None:
    needle = (needle or "").strip()
    if not needle:
        return None

    # Точный id (после заземления действий в chat_exec) — самый надёжный путь
    if len(needle) == 36 and "-" in needle:
        t = await db.get(Task, needle)
        if t and _can_touch(user, t.user_id):
            return t
        return None

    # Точное совпадение по названию (сначала среди своих)
    r = await db.execute(select(Task).where(Task.title.ilike(needle)))
    for t in r.scalars().all():
        if _can_touch(user, t.user_id):
            return t

    # Частичное совпадение
    r = await db.execute(select(Task).where(Task.title.ilike(f"%{needle}%")))
    for t in r.scalars().all():
        if _can_touch(user, t.user_id):
            return t

    return None


async def _find_schedule(db, user, needle: str) -> Schedule | None:
    needle = (needle or "").strip()
    if not needle:
        return None

    if len(needle) == 36 and "-" in needle:
        s = await db.get(Schedule, needle)
        if s and _can_touch(user, s.user_id):
            return s
        return None

    r = await db.execute(select(Schedule).where(Schedule.title.ilike(needle)))
    for s in r.scalars().all():
        if _can_touch(user, s.user_id):
            return s

    r = await db.execute(select(Schedule).where(Schedule.title.ilike(f"%{needle}%")))
    for s in r.scalars().all():
        if _can_touch(user, s.user_id):
            return s

    return None


# ── Парсеры значений ─────────────────────────────────────────────

def _parse_date(s) -> date | None:
    if not s:
        return None
    if isinstance(s, date):
        return s
    s = str(s).strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _parse_month(s) -> str | None:
    """Приводит значение к формату YYYY-MM."""
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%Y-%m", "%m.%Y", "%Y-%m-%d"):
        try:
            d = datetime.strptime(s, fmt)
            return d.strftime("%Y-%m")
        except ValueError:
            continue
    return None


def _resolve_period(p: dict):
    """Определяет период задачи из параметров действия.

    Поддерживает:
      due_date  -> конкретный день «2026-09-25»
      due_month -> месяц «2026-09»
      due_year  -> год  «2026»
      period    -> человекочитаемо: «сентябрь», «сентябрь 2026», «2026», «завтра»…

    Возвращает (scope, due_date, due_month, due_year, текстовая_подпись).
    При ошибке возвращает ("error", None, None, None, сообщение).
    """
    raw_period = str(p.get("period") or "").strip().lower()

    # 1. Явно указанные поля
    month = _parse_month(p.get("due_month"))
    year = None
    if p.get("due_year") is not None:
        try:
            year = int(p["due_year"])
        except (TypeError, ValueError):
            year = None
    day = _parse_date(p.get("due_date"))

    # 2. Разбор текстового периода
    if raw_period and not (day or month or year):
        # Только год: «2026»
        if re.fullmatch(r"\d{4}", raw_period):
            year = int(raw_period)
        # Месяц и год: «сентябрь 2026», «сентябрь»
        else:
            month_names = {
                "январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "май": 5,
                "июн": 6, "июл": 7, "август": 8, "сентябр": 9, "октябр": 10,
                "ноябр": 11, "декабр": 12,
            }
            found_month = None
            for stem, num in month_names.items():
                if stem in raw_period:
                    found_month = num
                    break
            year_match = re.search(r"(20\d{2})", raw_period)
            found_year = int(year_match.group(1)) if year_match else None

            relative = {
                "сегодня": 0, "завтра": 1, "послезавтра": 2,
            }
            if raw_period in relative:
                day = date.today() + timedelta(days=relative[raw_period])
            elif found_month:
                y = found_year or date.today().year
                month = f"{y:04d}-{found_month:02d}"
            elif found_year:
                year = found_year

    # 3. Определяем scope
    if p.get("scope") in ("month", "месяц"):
        scope = TaskScope.MONTH
    elif p.get("scope") in ("year", "год"):
        scope = TaskScope.YEAR
    elif month:
        scope = TaskScope.MONTH
    elif year:
        scope = TaskScope.YEAR
    elif day:
        scope = TaskScope.DAY
    else:
        scope = TaskScope.NONE

    # 4. Оставляем только поле, соответствующее периоду
    if scope == TaskScope.MONTH and not month:
        return "error", None, None, None, "Не удалось определить месяц задачи"
    if scope == TaskScope.YEAR and not year:
        return "error", None, None, None, "Не удалось определить год задачи"

    due_date = day if scope == TaskScope.DAY else None
    due_month = month if scope == TaskScope.MONTH else None
    due_year = year if scope == TaskScope.YEAR else None

    label = _period_label(scope, due_date, due_month, due_year)
    return scope, due_date, due_month, due_year, label


def _period_label(scope, due_date, due_month, due_year) -> str:
    if scope == TaskScope.DAY and due_date:
        return f", срок {due_date.strftime('%d.%m.%Y')}"
    if scope == TaskScope.MONTH and due_month:
        return f", на месяц {_month_ru(due_month)}"
    if scope == TaskScope.YEAR and due_year:
        return f", на {due_year} год"
    return " (без срока)"


_MONTHS_RU = [
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
]


def _month_ru(ym: str) -> str:
    """«2026-09» -> «сентябрь 2026»."""
    try:
        y, m = int(ym[:4]), int(ym[5:7])
        return f"{_MONTHS_RU[m - 1]} {y}"
    except Exception:
        return ym


def _parse_time(s) -> time:
    parts = str(s).strip().split(":")
    return time(int(parts[0]), int(parts[1]))


def _parse_status(s) -> TaskStatus | None:
    s = str(s).lower().strip()
    mapping = {
        "pending": TaskStatus.PENDING,
        "к выполнению": TaskStatus.PENDING,
        "новая": TaskStatus.PENDING,
        "in_progress": TaskStatus.IN_PROGRESS,
        "в работе": TaskStatus.IN_PROGRESS,
        "выполняется": TaskStatus.IN_PROGRESS,
        "done": TaskStatus.DONE,
        "выполнена": TaskStatus.DONE,
        "выполнено": TaskStatus.DONE,
        "готово": TaskStatus.DONE,
        "overdue": TaskStatus.OVERDUE,
        "просрочено": TaskStatus.OVERDUE,
    }
    return mapping.get(s)


def _parse_type(s) -> ScheduleType:
    s = str(s).lower()
    if s in ("meeting", "собрание", "встреча", "мероприятие"):
        return ScheduleType.MEETING
    if s in ("other", "другое", "иное"):
        return ScheduleType.OTHER
    return ScheduleType.LESSON


# ─── Утилита для API ─────────────────────────────────────────────

def actions_to_public(actions: list[dict]) -> list[dict]:
    """Убирает лишнее перед отправкой на клиент."""
    return [
        {
            "action": a.get("action"),
            "params": a.get("params", {}),
            "description": a.get("description", ""),
        }
        for a in actions
    ]
