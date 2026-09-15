"""Проверка дублей при импорте расписания.

Используется в:
- массовом распределении по преподавателям (управляющий, /chat/upload)
- подтверждении расписания на фронтенде (/schedule/batch)

Ключи уникальности считаются В РАЗРЕЗЕ преподавателя: одинаковая пара
у двух разных преподавателей — это не дубль.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_models import Schedule


def dup_key(title: str, day_of_week: int, start_time: str, end_time: str, group_name: str = "",
            event_date: str = "", weeks: str = "") -> str:
    """Ключ уникальности пары внутри расписания одного преподавателя.

    event_date различает «шаблон на среду» и «занятие на конкретную среду»;
    weeks различает верх/низ недели (одно время, но разные недели семестра).
    """
    t = (title or "").strip().lower()
    g = (group_name or "").strip().lower()
    s = str(start_time or "")[:5]
    e = str(end_time or "")[:5]
    try:
        d = int(day_of_week)
    except (TypeError, ValueError):
        d = -1
    dt = str(event_date or "")[:10]
    wk = (weeks or "").strip().lower().replace(" ", "")
    return f"{t}|{d}|{s}|{e}|{g}|{dt}|{wk}"


def item_key(item: dict) -> str:
    """Ключ для элемента импорта или из API."""
    return dup_key(
        item.get("title", ""),
        item.get("day_of_week", 0),
        item.get("start_time", ""),
        item.get("end_time", ""),
        item.get("group_name", ""),
        item.get("event_date", "") or "",
        item.get("weeks", "") or "",
    )


async def load_existing_keys(db: AsyncSession, user_id: str) -> set[str]:
    """Все ключи существующих пар преподавателя."""
    result = await db.execute(select(Schedule).where(Schedule.user_id == user_id))
    keys = set()
    for s in result.scalars().all():
        keys.add(dup_key(
            s.title,
            s.day_of_week,
            s.start_time.strftime("%H:%M"),
            s.end_time.strftime("%H:%M"),
            s.group_name,
            s.event_date.isoformat() if s.event_date else "",
            s.weeks or "",
        ))
    return keys


class DuplicateTracker:
    """Отслеживает дубли по каждому преподавателю отдельно.

    Учитывает и то, что уже есть в календаре, и повторы внутри одного импорта.
    """

    def __init__(self) -> None:
        self._keys: dict[str, set[str]] = {}
        self.skipped = 0

    async def prime(self, db: AsyncSession, user_id: str) -> None:
        """Загружает текущее расписание преподавателя."""
        self._keys.setdefault(user_id, set()).update(await load_existing_keys(db, user_id))

    def is_duplicate(self, user_id: str, item: dict) -> bool:
        bucket = self._keys.setdefault(user_id, set())
        key = item_key(item)
        if key in bucket:
            self.skipped += 1
            return True
        bucket.add(key)
        return False

    def mark(self, user_id: str, item: dict) -> None:
        """Отметить пару как добавленную."""
        self._keys.setdefault(user_id, set()).add(item_key(item))

    def count_for(self, user_id: str) -> int:
        return len(self._keys.get(user_id, set()))