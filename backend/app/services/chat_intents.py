"""Единый детектор детерминированных намерений чата.

Вместо бывших regex-«режимов», раскиданных по /upload и /send: один вход,
один выход — структурированное намерение (или None → AI-слой).

Намерения, привязанные к активному импорту (ScheduleImport):
  import_week   — ответ «на ближайшую неделю»
  import_semester(date) — ответ «на семестр до 30.12» / «до 30 декабря»
  import_cancel — «отмена»
Намерения по данным импорта (нужен импорт в состоянии READY):
  add_pairs(fio)     — «добавь пары ФИО [ко мне]» (замещение: в свой календарь)
  transfer(fio)      — «перенеси пары ФИО в её/его календарь» / «в календарь ФИО»
  transfer(fio, to)  — «перенеси пары Федуловой к Шапуленковой»: занятия ОДНОГО
                       преподавателя из файла — в календарь ДРУГОГО аккаунта
  distribute()       — «распредели всем преподавателям»
Прочие (работают без импорта, на живом календаре):
  clear(scope)       — «очисти календарь [полностью|завтра|в среду|с Д по Д]»,
                       менеджеру — и с адресатом: «очисти у ФИО ...»
None — вопрос/болтовня/одиночные операции — в AI-слой (он заземлён на БД).
"""
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from app.services.teacher_matcher import (
    detect_distribute_all, detect_transfer_target, extract_target_teacher,
)

__all__ = ["Intent", "detect_intent", "parse_date_loose", "parse_clear_scope"]

_ADD_VERB_RE = re.compile(
    r"(добав|прибав|перенес|занес|внес|полож|закинь|разнес|разлож|распредели|раздай|сохрани|поставь|поставьте|положите)",
    re.IGNORECASE,
)
_QUESTION_RE = re.compile(
    r"(сколько|когда\s|покажи|какие\b|какой\b|какая\b|какие\s+у\s+меня|есть\s+ли|освобод|напомни|что\s+у\s+меня)",
    re.IGNORECASE,
)
_CLEAR_RE = re.compile(r"(очист|очисти|удали\s+(?:все|у\s)|удалить\s+(?:все|у\s)|убер[и]?\s+у\s|сбрось|сотри|почист)", re.IGNORECASE)
_CANCEL_RE = re.compile(r"^\s*(отмена|отменить|отмена[.!]?\s*$|не надо|не нужно|отставить|cancel)\s*[.!]*\s*$",
                        re.IGNORECASE)
_ANSWER_WEEK_RE = re.compile(r"\b(на\s+(ближайшую\s+)?неделю|только\s+неделю|одну\s+неделю|на\s+эту\s+неделю|на\s+следующую\s+неделю|неделю)\b", re.IGNORECASE)
_ANSWER_SEM_RE = re.compile(r"\b(на\s+семестр|весь\s+семестр|до\s+конца\s+семестра|семестр)\b", re.IGNORECASE)
# «начни неделю-1 с 8 сентября» / «неделя 1 = с 14.09» — сдвиг якоря развёртки
_ANCHOR_RE = re.compile(r"(?:начни|считай|отсчитывай|веди)?\s*недел[яю]\s*-?\s*1\b[^.]{0,20}?(?:с|от)\s+([0-9а-яё.\s]{3,22})",
                        re.IGNORECASE)

# «перенеси пары Федуловой к Шапуленковой» — от кого (из файла) → кому (аккаунт).
# Имена допускаются в любом падеже и регистре; стоп-слова отсекают «на пятницу».
_TRANSFER_BETWEEN_RE = re.compile(
    r"(?:[Пп]еренес[а-яё]*|[Пп]ерекинь|[Пп]ерекиньте|[Пп]еренаправ[а-яё]*)\s+"
    r"(?:вс[ееё]\s+)?(?:пар[а-яё]*|заняты[а-яё]*|заняти[а-яё]*|расписани[а-яё]*)?\s*"
    r"(?P<from>(?:[А-ЯЁ][а-яё]{2,}|[а-яё]{4,})(?:\s+[А-ЯЁ]\.\s?[А-ЯЁ]?\.?)?)\s+"
    r"(?:[Кк]|[Вв]|[Нн]а)\s+(?:[Кк]алендар[а-яё]+|[Рр]асписание)?\s*"
    r"(?P<to>(?:[А-ЯЁ][а-яё]{2,}|[а-яё]{4,})(?:\s+[А-ЯЁ]\.\s?[А-ЯЁ]?\.?)?)"
)
# слова, которые не могут быть фамилиями в этой конструкции
_NOT_A_NAME = {
    "пары", "пару", "парам", "занятия", "занятие", "занятий", "расписание", "расписания",
    "календарь", "календаря", "календарю", "сетку", "файл", "файла", "себя", "нее", "неё",
    "нему", "ней", "него", "него", "мне", "его", "их", "ней", "ней", "всё", "все", "всю",
    "преподавателя", "преподавателю", "учителя", "учителю", "коллеги", "коллеге",
    "компотентную", "кабинет", "группу", "группы", "предмет", "партию", "пятницу",
}


def extract_transfer_between(message: str) -> tuple[str, str]:
    """«перенеси пары X к Y» → (X, Y); не нашло — ('', '')."""
    m = _TRANSFER_BETWEEN_RE.search(message or "")
    if not m:
        return "", ""
    if not re.search(r"(пар|занят|расписан)", message, re.IGNORECASE):
        return "", ""
    src = (m.group("from") or "").strip()
    dst = (m.group("to") or "").strip()
    low_s, low_d = src.lower(), dst.lower()
    if low_s in _NOT_A_NAME or low_d in _NOT_A_NAME:
        return "", ""
    if any(low_s.startswith(w) or low_d.startswith(w) for w in WDAYS if len(w) >= 3):
        return "", ""
    if re.search(r"(?:^|\s)(?:ко|к)\s+мне\b|на\s+себя\b", message, re.IGNORECASE):
        return "", ""  # «ко мне» — это add_pairs (замещение), не transfer между
    return src, dst


@dataclass
class Intent:
    kind: str
    fio: str = ""
    scope: dict = field(default_factory=dict)
    # текст ответа/пояснение для отчёта в чате
    note: str = ""


# ── Dates «на слух» ───────────────────────────────────────────────

MONTHS = {
    "янв": 1, "февр": 2, "фев": 2, "мар": 3, "апр": 4, "ма": 5, "мая": 5, "май": 5,
    "июн": 6, "июл": 7, "авг": 8, "сент": 9, "окт": 10, "нояб": 11, "дек": 12,
}
WDAYS = {
    "понедельник": 0, "понед": 0, "пн": 0, "вторник": 1, "вторн": 1, "вт": 1,
    "среду": 2, "среда": 2, "ср": 2, "четверг": 3, "чтв": 3, "чт": 3,
    "пятницу": 4, "пятница": 4, "пт": 4, "субботу": 5, "суббота": 5, "сб": 5,
    "воскресенье": 6, "воскресение": 6, "вс": 6,
}


def parse_date_loose(text: str, today: date | None = None) -> date | None:
    """'30.12', '30 декабря', '2026-12-30', 'до 15 мая' → date (год угадывается)."""
    today = today or date.today()
    t = (text or "").strip().lower()
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", t)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.search(r"(\d{1,2})[.](\d{1,2})[.](\d{2,4})", t)
    if m:
        dd, mm, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if yy < 100:
            yy += 2000
        try:
            d = date(yy, mm, dd)
            return d
        except ValueError:
            return None
    # ДД.ММ без года — ближайший год, начиная с текущего
    m = re.fullmatch(r"\s*(\d{1,2})[.](\d{1,2})\.?", t)
    if m:
        dd, mm = int(m.group(1)), int(m.group(2))
        for yy in (today.year, today.year + 1, today.year - 1):
            try:
                return date(yy, mm, dd)
            except ValueError:
                continue
        return None
    m = re.search(r"(\d{1,2})\s+([а-яё]{2,9})", t)
    if m:
        dd = int(m.group(1))
        mon = m.group(2)
        mm = None
        for k, v in MONTHS.items():
            if mon.startswith(k):
                mm = v
                break
        if mm:
            cands = []
            for yy in (today.year, today.year + 1):
                try:
                    cands.append(date(yy, mm, dd))
                except ValueError:
                    continue
            if cands:
                # дата в пределах полугода назад — это «этот год» (якорь семестра
                # мог быть и на прошлой неделе); дальше назад — берём будущую
                base = today - timedelta(days=183)
                ok = [d for d in cands if d >= base]
                return min(ok) if ok else max(cands)
    if "завтра" in t:
        return today + timedelta(days=1)
    return None


def parse_clear_scope(text: str, today: date | None = None) -> dict:
    """Из текста «очисти ...» выжимает временной селектор: {} = полностью.

    Порядок важен: сначала конкретика (диапазон/день/дата), и только если её
    нет — пустой dict (= «полностью»). Поэтому фразы «все пары», «полностью»
    отдельно проверять не нужно: они и так ни во что временное не попадают.
    """
    today = today or date.today()
    t = (text or "").lower()
    m = re.search(r"(\d{1,4}[.]\d{1,2}([.]\d{2,4})?|[а-яё0-9.\-]+\s+[а-яё]+\s+\d{4}|\d{4}-\d{2}-\d{2}|"
                  r"\d{1,2}\s*[а-яё]{2,6}|завтра|сегодня|послезавтра)\s*по\s*"
                  r"(\d{1,4}[.]\d{1,2}([.]\d{2,4})?|\d{4}-\d{2}-\d{2}|\d{1,2}\s*[а-яё]{2,6}|послезавтра|завтра|сегодня)", t)
    if m:
        d1 = parse_date_loose(m.group(1), today)
        d2 = parse_date_loose(m.group(3), today)
        if d1 and d2:
            if d1 > d2:
                d1, d2 = d2, d1
            return {"from": d1.isoformat(), "to": d2.isoformat()}
    # Сначала явный день недели («в среду», «по пятницам») — он встречается чаще,
    # чем «на этой неделе», и не должен им перекрываться.
    m = re.search(r"\b(?:в|по|за)\s+(понедельник|понед|пн|вторник|вторн|вт|среду|среда|ср|четверг|чтв|чт|пятницу|пятница|пт|субботу|суббота|сб|воскресенье|воскресение|вс)\b", t)
    if m:
        wd = WDAYS.get(m.group(1))
        if wd is not None:
            return {"weekday": wd}
    if "завтра" in t:
        d = today + timedelta(days=1)
        return {"from": d.isoformat(), "to": d.isoformat()}
    if "послезавтра" in t:
        d = today + timedelta(days=2)
        return {"from": d.isoformat(), "to": d.isoformat()}
    if re.search(r"\bсегодня\b|сегодняшн", t):
        return {"from": today.isoformat(), "to": today.isoformat()}
    if "следующ" in t and "недел" in t:
        mon = today + timedelta(days=7 - today.weekday())
        return {"from": mon.isoformat(), "to": (mon + timedelta(days=6)).isoformat()}
    if re.search(r"(на\s+этой\s+неделе|эту\s+неделю|этой\s+недели)", t):
        mon = today - timedelta(days=today.weekday())
        return {"from": mon.isoformat(), "to": (mon + timedelta(days=6)).isoformat()}
    m = re.search(r"\b(\d{1,2}[.]\d{1,2}([.]\d{2,4})?|\d{4}-\d{2}-\d{2})\b", t)
    if m:
        d = parse_date_loose(m.group(1), today)
        if d:
            return {"from": d.isoformat(), "to": d.isoformat()}
    m = re.search(r"\b(\d{1,2}\s+(?:янв|февр|фев|мар|апр|ма[йя]|июн|июл|авг|сент|окт|нояб|дек)[а-яё]*)\b", t)
    if m:
        d = parse_date_loose(m.group(1), today)
        if d:
            return {"from": d.isoformat(), "to": d.isoformat()}
    return {}  # без уточнения — «полностью» (в карточке будет видно)


# ── Публикация новости (менеджер/админ) ───────────────────────────

_NEWS_PUBLISH_RE = re.compile(
    r"\b(?:опублику[йи](?:те)?|опубликую|вылож[иу](?:те)?|выложить|"
    r"разме[щш][ауие](?:те)?|размест[ии](?:те)?|разместить|"
    r"добав[ьи](?:те)?|добавить|анонсиру[йи](?:те)?|анонсирую)\s+"
    r"(?:(?:новую|следующую|свежую|важную)\s+)?новост(?:ь|и|ку|ей)\b",
    re.IGNORECASE)


def extract_news_text(message: str) -> str:
    """«опубликуй новость - "текст"» → 'текст'. Пусто, если текста нет."""
    m = _NEWS_PUBLISH_RE.search(message or "")
    if not m:
        return ""
    rest = message[m.end():]
    rest = re.sub(r"^\s*(?:—|–|-{1,2}|:|—\s*:)?\s*", "", rest)
    rest = rest.strip()
    for op, cl in (("«", "»"), ("\u201c", "\u201d"), ("\u201e", "\u201c"), ('"', '"'), ("'", "'")):
        if rest.startswith(op) and rest.endswith(cl) and len(rest) > 2:
            rest = rest[1:-1]
            break
    return rest.strip()


# ── Главный детектор ──────────────────────────────────────────────

def detect_intent(message: str, *, import_state: str = "", today: date | None = None) -> Intent | None:
    """import_state — состояние АКТИВНОГО импорта пользователя ('' если нет)."""
    m = message.strip()
    if not m:
        return None
    low = m.lower()

    if _CANCEL_RE.match(m):
        if import_state in ("ASK_PERIOD", "ASK_END", "READY"):
            return Intent("import_cancel")
        return None

    # Очистка календаря — важнее продолжения машины состояний
    # («очисти календарь на этой неделе» при висящем вопросе = чистка, не ответ).
    if _CLEAR_RE.search(low) and re.search(r"(календар|расписани|пар|заняти|задач|нот)", low):
        target = extract_target_teacher(m)
        return Intent("clear", fio=target, scope=parse_clear_scope(m, today))

    # Явная команда публикации новости — важнее машины состояний импорта.
    if _NEWS_PUBLISH_RE.search(m):
        return Intent("publish_news", scope={"text": extract_news_text(m)})

    # Продолжение машины состояний активного импорта.
    # READY тоже принимает переразвёртку: пользователь мог передумать.
    if import_state in ("ASK_PERIOD", "ASK_END", "READY"):
        a = _ANCHOR_RE.search(m)
        if a:
            ad = parse_date_loose(a.group(1), today)
            if ad:
                return Intent("import_anchor", scope={"anchor": ad.isoformat()})
        if _ANSWER_WEEK_RE.search(low):
            return Intent("import_week", note="на ближайшую неделю")
        if _ANSWER_SEM_RE.search(low):
            d = parse_date_loose(low, today)
            if d:
                return Intent("import_semester", scope={"end": d.isoformat()})
            return Intent("import_semester_ask_end")
        if import_state in ("ASK_END", "READY") and re.search(r"\bдо\s+\d", low):
            d = parse_date_loose(m, today)
            if d:
                return Intent("import_semester", scope={"end": d.isoformat()})
    if import_state == "ASK_END":
        d = parse_date_loose(m, today)
        if d:
            return Intent("import_semester", scope={"end": d.isoformat()})

    # Всё, что ниже, требует данных импорта — решает вызывающий (нет импорта → None)
    if _QUESTION_RE.search(m) and not _ADD_VERB_RE.search(m):
        return None
    if not _ADD_VERB_RE.search(m):
        return None

    if detect_distribute_all(m):
        return Intent("distribute")

    # сначала двухчастный перенос «X → к Y» (оба имени в одной фразе)
    src, dst = extract_transfer_between(m)
    if src and dst:
        return Intent("transfer", fio=src, scope={"to": dst})

    target = extract_target_teacher(m)
    transfer = detect_transfer_target(m, target)
    if transfer:
        return Intent("transfer", fio=transfer)
    # одиночная пара «поставь завтра пару в 14:00» — не наше: без ФИО-импорта
    # пусть AI; у нас ADD-глагол без цели → None
    if target:
        return Intent("add_pairs", fio=target)
    return None
