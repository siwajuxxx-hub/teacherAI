"""Развёртка импорта расписания в КОНКРЕТНЫЕ ДАТЫ.

Два вида файлов:
- dated (docx-сессия, календарный PDF): items уже с event_date — проходят как есть;
- weekly (xls-сетка Пн-Вс): каждый шаблон размножается по неделям периода.
  Номера недель семестра считаются от «недели-1» (понедельник, который принял
  пользователь; по умолчанию — понедельник текущей недели). Поле item['weeks']
  ('3,7,11' | '2 по 12' | 'верх'/'низ' | пусто) фильтрует недели.
"""
import re
from datetime import date, timedelta

from app.services.schedule_dedup import item_key


def monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def week_number(day: date, first_monday: date) -> int:
    """Номер недели семестра (1-based), если неделя-1 начинается в first_monday."""
    return (monday_of(day) - first_monday).days // 7 + 1


def weeks_match(spec: str | None, n: int) -> bool:
    """Проходит ли шаблон с weeks=spec в неделю номер n.

    Примеры spec: '3,7,11,15' | '2 по 12' | '3,7; 11 по 15' | 'верх'/'низ'
    ('верх' — чётные ISO-недели, «низ» — нечётные; конвенция настраивается
    единожды и показывается в отчёте).
    """
    if not spec or not spec.strip():
        return True
    for token in re.split(r"[;,]", spec):
        t = token.strip().lower()
        if not t:
            continue
        if t in ("верх", "верхн", "верхняя", "чётн", "четн", "odd"):
            if n % 2 == 0:
                return True
            continue
        if t in ("низ", "нижн", "нижняя", "нечётн", "ечётн", "even"):
            if n % 2 == 1:
                return True
            continue
        nums = re.findall(r"\d+", t)
        if not nums:
            continue  # нераспознанный маркер — считаем «любая неделя»
        if "по" in t and len(nums) >= 2:
            lo, hi = sorted((int(nums[0]), int(nums[1])))
            if lo <= n <= hi:
                return True
        else:
            if n in {int(x) for x in nums}:
                return True
    return False


def expand_items(items: list[dict], *, first_monday: date, start: date, end: date) -> list[dict]:
    """Items (смесь шаблонов и dated) → только items с event_date в [start..end].

    - dated (есть event_date): включаем как есть (вне диапазона — тоже: они
      самодостаточны, пользователь их явно по датам и загрузил);
    - weekly-шаблоны: копируются на каждую подходящую неделю, поле weeks
      с шаблона на дату не переносится.
    """
    out: list[dict] = []
    templates: dict[int, list[dict]] = {}
    for it in items:
        if it.get("event_date"):
            out.append(dict(it))
        else:
            templates.setdefault(int(it.get("day_of_week", 0)), []).append(it)

    if not templates:
        return out

    seen_keys = {item_key(o) for o in out}
    week_start = monday_of(start)  # недели идём от понедельника, но окно — строгое
    while week_start <= end:
        n = week_number(week_start, first_monday)
        if n >= 1:
            for dow, tlist in templates.items():
                day = week_start + timedelta(days=dow)
                if day < start or day > end:
                    continue
                for tpl in tlist:
                    if not weeks_match(tpl.get("weeks"), n):
                        continue
                    dated = {k: v for k, v in tpl.items() if k != "weeks"}
                    dated["event_date"] = day.isoformat()
                    # разные шаблоны верх/низ на одну дату и время не должны
                    # плодить двойные записи
                    key = item_key(dated)
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    out.append(dated)
        week_start += timedelta(days=7)
    return out


def next_week_window(today: date | None = None) -> tuple[date, date]:
    """«Ближайшая неделя»: с сегодня ровно 7 дней."""
    t = today or date.today()
    return t, t + timedelta(days=6)
