"""Детерминированный парсер расписания из Word-документов (.docx).

Формат (проверен на «3 курс заочная, установочная сессия»):
- в документе может быть НЕСКОЛЬКО таблиц-расписаний (свои группы у каждой);
- шапка: колонки — коды групп с численностью «ЭС1-24з (29)», «ТМ1(ПИ)-24з (11)»;
- строки: col0 = «21.09.26 понед.» (конкретная ДАТА), col1 = «2 пара 10.15-11.45»;
- ячейка = «лк Предмет доц. Фамилия И.О. [N пгр.] [А/Б/В ]ауд» (Несколько занятий
  — с новой строки); ГОРИЗОНТАЛЬНЫЕ СЛИЯНИЯ python-docx отдаёт повтором текста
  ячейки → одна запись попадает в обе группы-column;
- переносы слов с дефисом («авто-матизация») склеиваются.

Выход — items как у xls-парсера, но с заполненным event_date (kind = dated).
"""
import io
import re
from datetime import date, datetime

from app.services.xls_schedule_parser import (
    MARKER_LABEL, SLOT_RE, TEACHER_RE, WEEK_LIST_RE, WEEK_SPAN_RE,
    _finalize_record, _split_records,
)

# Группа в шапке docx-таблицы: «ЭС1-24з (29)», «ТМ1(ПИ)-24з (11)»
DOCX_GROUP_RE = re.compile(r"^([А-ЯЁ][А-ЯЁа-яё0-9()\-/]{1,17})\s*\(\d{1,3}\)\s*$")

# Дата строки: «21.09.26 понед.» / «01.10.26 четверг»
ROW_DATE_RE = re.compile(r"^\s*(\d{1,2})\.(\d{1,2})\.(\d{2,4})")

# Номер пары: «2 пара 10.15-11.45»
PARA_RE = re.compile(r"(\d{1,2})\s*пара", re.IGNORECASE)

PGR_NUM_RE = re.compile(r"\b(\d)\s*пгр\.?\b")


def _join_hyphens(text: str) -> str:
    """Склеивает переносы «-\\n»: «авто-\\nматизация» → «автоматизация»."""
    return re.sub(r"([а-яёA-ЯЁ])-\s*\n\s*([а-яёA-ЯЁ])", r"\1\2", text)


def _parse_row_date(text: str):
    m = ROW_DATE_RE.match(text or "")
    if not m:
        return None
    dd, mm, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if yy < 100:
        yy += 2000
    try:
        return date(yy, mm, dd)
    except ValueError:
        return None


def _cell_text(cell) -> str:
    return _join_hyphens((cell.text or "").replace("\r", "").strip())


def _parse_table(idx: int, table) -> list[dict]:
    rows = table.rows
    if len(rows) < 3 or not rows:
        return []

    # Шапка групп — первая строка, где >=2 колонок с «код (численность)»
    groups: dict[int, str] = {}
    for ci, cell in enumerate(rows[0].cells):
        t = _cell_text(cell)
        m = DOCX_GROUP_RE.match(t)
        if m:
            groups[ci] = m.group(1)
    if len(groups) < 2:
        return []

    items: list[dict] = []
    prev_day: date | None = None  # вертикальные слияния col0: дата «тянется» вниз
    prev_slot: tuple[str, str] | None = None
    for row in rows[1:]:
        cells = row.cells
        day = _parse_row_date(_cell_text(cells[0])) if cells else None
        if day:
            prev_day = day
        day = day or prev_day
        if not day:
            continue

        slot_text = _cell_text(cells[1]) if len(cells) > 1 else ""
        ms = SLOT_RE.search(slot_text)
        if ms:
            prev_slot = (f"{int(ms.group(1)):02d}:{ms.group(2)}", f"{int(ms.group(3)):02d}:{ms.group(4)}")
        slot = prev_slot if (ms is None and slot_text == "") else (prev_slot if ms else None)
        if ms is None and slot_text:  # строка без времени (например «окно») — слота нет
            slot = None
        if not slot:
            continue

        for ci, gname in groups.items():
            if ci >= len(cells):
                continue
            text = _cell_text(cells[ci])
            if not text:
                continue
            pgr = PGR_NUM_RE.search(text)
            group = f"{gname} ({pgr.group(1)} пгр.)" if pgr else gname
            for rec in _split_records([text]):
                fin = _finalize_record(" ".join(rec.parts))
                if not fin:
                    continue
                title = fin["subject"]
                if fin["marker"]:
                    title = f"{title} ({fin['marker']})"
                for teacher in fin["teachers"]:
                    items.append({
                        "title": title,
                        "day_of_week": day.weekday(),
                        "event_date": day.isoformat(),
                        "start_time": slot[0],
                        "end_time": slot[1],
                        "group_name": group,
                        "room": " / ".join(fin["rooms"]),
                        "type": "lesson",
                        "teacher": teacher,
                        "source": "docx_import",
                        "sheet": f"table#{idx}",
                    })
    return items


def parse_docx_schedule(file_bytes: bytes, filename: str = "") -> list[dict]:
    """Парсит docx-расписание. [] — если структурно не похоже (откат на AI)."""
    try:
        from docx import Document
        doc = Document(io.BytesIO(file_bytes))
    except Exception:
        return []

    items: list[dict] = []
    for i, table in enumerate(doc.tables):
        try:
            items.extend(_parse_table(i, table))
        except Exception:
            continue

    # Дедуп внутри файла (в т.ч. повтор от слияний ячеек)
    seen, uniq = set(), []
    for it in items:
        key = (it["teacher"].lower(), it["event_date"], it["start_time"],
               it["title"].lower(), it["group_name"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(it)
    return uniq


def extract_docx_text(file_bytes: bytes) -> str:
    """Текстовый дамп (para + tables) — для AI-отката."""
    from app.services.file_parser import _extract_docx
    return _extract_docx(file_bytes)
