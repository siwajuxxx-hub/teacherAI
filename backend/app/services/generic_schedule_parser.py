"""Универсальный парсер расписаний из таблиц ЛЮБОЙ раскладки — без AI.

Три режима, по убыванию надёжности:
 1. Таблица с заголовками («День / Время / Предмет / Группа / Преподаватель / Ауд.») —
    колонки сопоставляются по ключевым словам, строки читаются под заголовком.
 2. Таблица без заголовков — каждую строку разбираем эвристикой: ищем день недели,
    дату, интервал времени, ФИО, группу, аудиторию; самый «словесный» остаток — предмет.
 3. Вертикальные блоки с переносом: день/дата/группа, заданные один раз для блока,
    переносятся на следующие строки (частый случай объединённых ячеек в Excel).

Поддерживает: .xls/.xlsx (через загрузчик сеток из xls_schedule_parser),
.docx (таблицы python-docx), .csv/.tsv, просто текстовые строки списком.
Если ничего не распознано — вызывающий волен послать текст в AI.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date

from app.services.chat_intents import WDAYS, parse_date_loose
from app.services.xls_schedule_parser import _cell_text, _load_grids

__all__ = ["parse_generic_file", "parse_rows", "rows_from_csv", "rows_from_docx"]

# «9:30 — 11:00» / «9.30-11.00» / «09:30–11:00»
TIME_RANGE_RE = re.compile(r"\b(\d{1,2})[:.](\d{2})\s*[-–—]\s*(\d{1,2})[:.](\d{2})\b")
TIME_ONE_RE = re.compile(r"\b(\d{1,2}):(\d{2})\b")
DATE_RE = re.compile(r"\b\d{1,2}[.]\d{1,2}(?:[.]\d{2,4})?\b")
FIO_RE = re.compile(r"\b([А-ЯЁ][а-яё]{2,}(?:\s+[А-ЯЁ]\.\s?[А-ЯЁ]\.?|\s+[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ]\.))")
GROUP_RE = re.compile(
    r"\b(?:[А-ЯЁA-Z]{1,6}\d?[–-]\d{1,3}[а-яё]?|[А-ЯЁA-Z]{2,6}\d{2,3}[а-яё]?)\b")
ROOM_RE = re.compile(r"^(?:ауд\.?\s*)?(\d{1,4}[а-яё]?)$", re.IGNORECASE)
LESSON_NUM_RE = re.compile(r"^\s*(\d{1,2})\s*(?:пара|пары|\.|-)?\s*$", re.IGNORECASE)
_DAY_KEYS = sorted((k for k in WDAYS if len(k) >= 2), key=len, reverse=True)
DAY_ANY_RE = re.compile(r"(?<![а-яёa-z])(%s)(?![а-яёa-z])" % "|".join(_DAY_KEYS),
                        re.IGNORECASE)

# окна стандартных пар (№ пары → начало); длительность 1:30
PAIR_STARTS = ["09:00", "10:50", "12:40", "14:30", "16:20", "18:10", "19:00"]

HEADER_ROLES: dict[str, tuple[str, ...]] = {
    "day": ("день",),
    "date": ("дата", "число"),
    "time": ("время", "начало", "начала"),
    "lesson_no": ("№ пар", "номер пар", "пара"),
    "title": ("предмет", "дисциплин", "занят", "название"),
    "group": ("групп",),
    "teacher": ("преподавател", "лектор", "препод", "фио", "ведущий"),
    "room": ("аудит", "ауд", "комнат", "помещени"),
}
SKIP_CELL_RE = re.compile(r"^(?:[-–—.\s]*|вс|итого|обед)$", re.IGNORECASE)


def _t(h: str, m: str) -> str:
    return f"{int(h):02d}:{m}"


def _plus90(t: str) -> str:
    h, m = int(t[:2]), int(t[3:5])
    total = h * 60 + m + 90
    return f"{(total // 60) % 24:02d}:{total % 60:02d}"


def _day_word(cell: str) -> int | None:
    c = cell.strip().lower().rstrip(".")
    return WDAYS.get(c)


def _extract_cells(cells: list[str], today: date | None) -> dict | None:
    """Разбор строки «в лоб» без карты колонок. None, если строка не занятие.

    День недели может отсутствовать (вернём day_of_week=None) — тогда его
    подставит carry-перенос из заголовка блока в parse_rows.
    """
    day = None
    dt = None
    start = end = None
    teacher = ""
    room = ""
    group = ""
    leftovers: list[str] = []
    for c in cells:
        s = (c or "").strip()
        if not s or SKIP_CELL_RE.match(s):
            continue
        used = False
        if day is None and len(s) <= 12:
            d = _day_word(s)
            if d is not None:
                day, used = d, True
        if not used and dt is None and DATE_RE.fullmatch(s):
            got = parse_date_loose(s, today)
            if got:
                dt, used = got, True
        if not used and start is None and TIME_RANGE_RE.search(s) and len(s) <= 24:
            m = TIME_RANGE_RE.search(s)
            start, end = _t(m.group(1), m.group(2)), _t(m.group(3), m.group(4))
            used = True
        if not used and not room and ROOM_RE.match(s):
            room, used = ROOM_RE.match(s).group(1), True
        if not used and not group and GROUP_RE.fullmatch(s):
            group, used = s, True
        if not used and not teacher and FIO_RE.fullmatch(s):
            teacher, used = s, True
        if not used:
            leftovers.append(s)

    joined = " | ".join(leftovers)
    if not teacher:
        m = FIO_RE.search(joined)
        if m:
            teacher = m.group(1).strip()
    if not group:
        m = GROUP_RE.search(joined)
        if m:
            group = m.group(0)
    if start is None:
        m = TIME_RANGE_RE.search(joined)
        if m:
            start, end = _t(m.group(1), m.group(2)), _t(m.group(3), m.group(4))
    if start is None:
        m = TIME_ONE_RE.search(joined)
        if m:
            start = _t(m.group(1), m.group(2))
    if start and not end:
        end = _plus90(start)
    # спасение из «грязной» строки-ячейки: дата/день могли не стать отдельными полями
    if dt is None:
        m = DATE_RE.search(joined)
        if m:
            dt = parse_date_loose(m.group(0), today)
    if day is None and dt is not None:
        day = dt.weekday()
    if not room:
        m = re.search(r"\b(?:ауд|аудитория|каб|кабинет|комн)\.?\s*(\d{1,4}[а-яё]?)",
                      joined, re.IGNORECASE)
        if m:
            room = m.group(1)
    if day is None:
        m = DAY_ANY_RE.search(joined)
        if m:
            day = WDAYS[m.group(1).lower()]
    # предмет — самый длинный остаток, не являющийся служебными полями
    title = ""
    for s in sorted(leftovers, key=len, reverse=True):
        if s.strip() == teacher or (group and GROUP_RE.fullmatch(s.strip())) or s.strip() == room:
            continue
        core = TIME_RANGE_RE.sub(" ", s)
        core = re.sub(r"\b\d{1,2}[:.]\d{2}\b", " ", core)
        core = DATE_RE.sub(" ", core)
        core = DAY_ANY_RE.sub(" ", core)
        core = FIO_RE.sub("", core)
        core = re.sub(r"\b[А-ЯЁA-Z]\.[А-ЯЁ]?\.", "", core)
        if group:
            core = core.replace(group, " ")
        if room:
            core = re.sub(rf"(?<!\w){re.escape(room)}(?!\w)", " ", core)
        core = re.sub(r"\b(?:ауд|аудитория|каб|кабинет|комн)\.?\b", " ", core, flags=re.IGNORECASE)
        if len(re.sub(r"\W+", "", core)) >= 4:
            title = re.sub(r"\s+", " ", core).strip(" ,.;-")
            break
    if not (title and start):
        return None
    return {"title": title[:500], "start_time": start, "end_time": end or _plus90(start),
            "day_of_week": day, "event_date": dt.isoformat() if dt else "",
            "group_name": group[:100], "room": room[:100], "teacher": teacher[:200],
            "type": "lesson"}


def _lesson_no_time(cells_row: list[str]) -> tuple[str, str] | None:
    for c in cells_row:
        m = LESSON_NUM_RE.match(c or "")
        if m and 1 <= int(m.group(1)) <= len(PAIR_STARTS):
            s = PAIR_STARTS[int(m.group(1)) - 1]
            return s, _plus90(s)
    return None


def parse_rows(rows: list[list[str]], today: date | None = None) -> list[dict]:
    """Список строк (списки ячеек-строк) → элементы расписания."""
    rows = [r for r in ([(c or "").strip() for c in row] for row in rows) if any(r)]
    if len(rows) < 2:
        return []

    # ── 1. режим с заголовками ─────────────────────────────────
    header_idx, colmap = -1, {}
    for i, row in enumerate(rows[:15]):
        found: dict[str, int] = {}
        for j, cell in enumerate(row):
            low = cell.lower().replace("\n", " ")
            for role, keys in HEADER_ROLES.items():
                if role in found:
                    continue
                if any(k in low for k in keys) and len(cell) <= 28:
                    found[role] = j
        if found.get("title") is not None and (
                found.get("time") is not None or found.get("lesson_no") is not None) \
                and (found.get("day") is not None or found.get("date") is not None):
            header_idx, colmap = i, found
            break

    items: list[dict] = []
    if header_idx >= 0:
        time_is_num = "time" not in colmap and "lesson_no" in colmap
        for row in rows[header_idx + 1:]:
            def g(role: str) -> str:
                j = colmap.get(role)
                return (row[j] if j is not None and j < len(row) else "").strip()

            day = _day_word(g("day")) if g("day") else None
            if day is None and g("day"):
                m = DATE_RE.search(g("day"))
                if m:
                    day_parsed = parse_date_loose(m.group(0), today)
                    if day_parsed:
                        day = day_parsed.weekday()
            dt = None
            m = DATE_RE.search(g("date") or g("day") or "")
            if m:
                dt = parse_date_loose(m.group(0), today)
            if day is None and dt is not None:
                day = dt.weekday()
            if day is None and dt is None:
                continue
            if time_is_num:
                tw = _lesson_no_time([g("lesson_no")])
                if not tw:
                    continue
                start, end = tw
            else:
                tr = TIME_RANGE_RE.search(g("time"))
                if tr:
                    start, end = _t(tr.group(1), tr.group(2)), _t(tr.group(3), tr.group(4))
                else:
                    one = TIME_ONE_RE.search(g("time"))
                    if not one:
                        continue
                    start = _t(one.group(1), one.group(2))
                    end = _plus90(start)
            title = g("title")
            if not title:
                continue
            teacher = g("teacher")
            if not teacher:  # ФИО могли попасть в предмет
                m = FIO_RE.search(title)
                if m:
                    teacher = m.group(1).strip()
                    title = FIO_RE.sub("", title).strip(" ,.;-")
            items.append({"title": title[:500], "start_time": start, "end_time": end,
                          "day_of_week": day,
                          "event_date": (dt.isoformat() if dt else ""),
                          "group_name": (g("group") or "")[:100],
                          "room": (g("room") or "")[:100],
                          "teacher": (teacher or "")[:200], "type": "lesson"})
        if len(items) >= 2:
            return _dedup(items)
        items = []

    # ── 2. эвристика по строкам с переносом «блока» ─────────────
    carry_day: int | None = None
    carry_date = ""
    carry_group = ""
    for row in rows:
        it = _extract_cells(row, today)
        if it is None:
            continue
        if it["day_of_week"] is None and carry_day is not None:
            it["day_of_week"] = carry_day
            it["event_date"] = carry_date
        elif it["day_of_week"] is not None:
            carry_day, carry_date = it["day_of_week"], it.get("event_date") or ""
        if it["group_name"]:
            carry_group = it["group_name"]
        elif not it["group_name"] and carry_group:
            it["group_name"] = carry_group
        if it["day_of_week"] is None:
            continue  # так и не узнали день — не заносим вслепую
        items.append(it)
    return _dedup(items)


def _dedup(items: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out = []
    for i in items:
        k = (i["title"].lower(), i["start_time"], i.get("event_date", ""), i["day_of_week"],
             i.get("group_name", "").lower())
        if k in seen:
            continue
        seen.add(k)
        out.append(i)
    return out


def rows_from_csv(b: bytes) -> list[list[str]]:
    text = _decode(b)
    first = (text.splitlines() or [""])[0]
    delim = max({";", ",", "\t", "|"}, key=first.count) if any(c in first for c in ";\t|") else ","
    try:
        return [list(r) for r in csv.reader(io.StringIO(text), delimiter=delim)]
    except Exception:
        return []


def rows_from_docx(file_bytes: bytes) -> list[list[str]]:
    from docx import Document
    d = Document(io.BytesIO(file_bytes))
    rows: list[list[str]] = []
    for t in d.tables:
        for r in t.rows:
            rows.append([c.text.replace("\u00a0", " ").strip() for c in r.cells])
    return rows


def _decode(b: bytes) -> str:
    for enc in ("utf-8-sig", "cp1251", "koi8-r"):
        try:
            return b.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return b.decode("utf-8", errors="replace")


def parse_generic_file(file_bytes: bytes, filename: str,
                       today: date | None = None) -> list[dict]:
    """Любой табличный/текстовый файл расписания → элементы (или [] если не похоже)."""
    ext = ("." + filename.rsplit(".", 1)[-1]).lower() if "." in filename else ""
    all_rows: list[list[str]] = []
    try:
        if ext in (".xls", ".xlsx"):
            try:
                for _name, grid in _load_grids(file_bytes, filename):
                    all_rows.extend(grid[:4000])
            except Exception:
                # «xls», который на деле текст/CSV
                txt = _decode(file_bytes)
                if re.search(r"\D", txt[:200]):
                    all_rows = rows_from_csv(file_bytes)
        elif ext == ".docx":
            all_rows = rows_from_docx(file_bytes)
        elif ext in (".csv", ".tsv", ".txt", ".md"):
            if ext == ".txt" or ext == ".md":
                all_rows = [[ln] for ln in _decode(file_bytes).splitlines()]
            else:
                all_rows = rows_from_csv(file_bytes)
    except Exception:
        return []
    if not all_rows:
        return []
    try:
        items = parse_rows(all_rows, today)
    except Exception:
        return []
    return items if len(items) >= 2 else (items if items else [])
