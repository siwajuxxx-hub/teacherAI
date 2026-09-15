"""Сопоставление имён преподавателей из расписания с пользователями системы."""
import re
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AuthSessionLocal
from app.models.auth_models import User, UserRole


# Слова-«шум» в ячейках расписания, которые не являются ФИО.
# ВАЖНО: удаляем только целые слова, иначе «доцента» превратилось бы в «ента».
NOISE_PREFIXES = [
    "ст.преп.", "ст.пр.", "ст.пр", "к.т.н.", "к.т.н", "д.т.н.", "д.т.н",
    "доц.", "доц", "асс.", "асс", "проф.", "проф", "пр.", "пр",
    "и.о.", "и.о", "зав.", "зав",
]

# Маркеры типов занятий (лк/лб/у/пз/сем) — убираем перед поиском ФИО
LESSON_TYPE_MARKERS = ["лк", "лб", "пз", "сем", "у"]


def clean_teacher_name(raw: str) -> str:
    """Убирает из строки звания и мусор, оставляя ФИО."""
    if not raw:
        return ""
    s = raw.strip()

    # Убираем звания только как отдельные слова (с границами).
    # Длинные варианты обрабатываем первыми, чтобы «ст.пр.» не разбилось на «пр.».
    # Полные формы («доцент», «профессор», «ассистент») — тоже.
    full_forms = ["доцент", "доцента", "доценты", "профессор", "профессора",
                  "ассистент", "ассистента", "преподаватель", "преподавателя",
                  "старший", "старшего", "кандидат", "доктор", "наук"]
    all_noise = sorted(NOISE_PREFIXES + full_forms, key=len, reverse=True)
    for noise in all_noise:
        pattern = r"(?<![А-Яа-яЁё])" + re.escape(noise) + r"(?![А-Яа-яЁё])"
        s = re.sub(pattern, " ", s, flags=re.IGNORECASE)

    # Убираем маркеры типа занятия в начале
    s = re.sub(r"^\s*(лк|лб|пз|сем|у)\s+", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip(" .,;|")
    # Схлопываем точки внутри инициалов: «Шапуленкова Е. К» → «Шапуленкова Е.К»
    s = re.sub(r"([А-ЯЁ])\.\s+([А-ЯЁ])(?=\s|$)", r"\1.\2", s)
    return s


def normalize_fio(name: str) -> str:
    """Нормализует ФИО: нижний регистр, без точек и лишних пробелов, ё→е."""
    if not name:
        return ""
    s = name.lower()
    s = s.replace(".", " ").replace(",", " ").replace("ё", "е")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def extract_surname(name: str) -> str:
    """Извлекает фамилию из ФИО (делает основу без падежного окончания)."""
    n = normalize_fio(name)
    if not n:
        return ""
    parts = n.split()
    # Ищем первое слово длиннее 3 символов — обычно фамилия
    for p in parts:
        if len(p) > 3 and p not in ("доц", "асс", "проф"):
            return _stem_surname(p)
    return _stem_surname(parts[0]) if parts else ""


def _stem_surname(surname: str) -> str:
    """Отбрасывает типичные падежные окончания русских фамилий:
    «Гаврилова» → «гаврилов», «Певцовой» → «певцов».
    """
    s = surname.lower()
    endings = ["ова", "ева", "ёва", "ина", "ына", "ая", "ого", "его", "ову", "еву", "ину", "ой", "ей", "ий"]
    for e in sorted(endings, key=len, reverse=True):
        if s.endswith(e) and len(s) - len(e) >= 4:
            return s[:-len(e)]
    # Для мужских фамилий на -ов/-ев/-ин убираем только если это падеж
    if s.endswith("ов") or s.endswith("ев") or s.endswith("ин") or s.endswith("ын"):
        return s
    return s


def names_match(name_a: str, name_b: str) -> bool:
    """Проверяет, относятся ли два ФИО к одному человеку (устойчиво к падежам)."""
    a = normalize_fio(name_a)
    b = normalize_fio(name_b)
    if not a or not b:
        return False
    if a == b:
        return True

    sur_a = extract_surname(name_a)
    sur_b = extract_surname(name_b)
    if not sur_a or not sur_b:
        return False
    if sur_a != sur_b:
        # Падежные формы дают разные основы: «Гаврилова»→«гаврил»,
        # «Гаврилов»→«гаврилов». Считаем совпадением, когда одна основа
        # начало другой (длина начала >= 4 — случайных пересечений мало).
        shorter, longer = (sur_a, sur_b) if len(sur_a) <= len(sur_b) else (sur_b, sur_a)
        if not (len(shorter) >= 4 and longer.startswith(shorter)):
            return False

    # Фамилии совпали — проверяем инициалы, если есть
    init_a = _initials(name_a)
    init_b = _initials(name_b)
    if init_a and init_b:
        return init_a[0] == init_b[0]
    return True


def _initials(name: str) -> str:
    """Собирает инициалы: «Гаврилов А.И.» → «аи»."""
    n = normalize_fio(name)
    parts = n.split()
    if len(parts) < 2:
        return ""
    return "".join(p[0] for p in parts[1:] if p)


async def find_user_by_teacher_name(db: AsyncSession, teacher_name: str) -> Optional[User]:
    """Находит пользователя-преподавателя по ФИО из расписания.

    ВАЖНО: пользователи хранятся в auth.db, поэтому используем отдельную сессию.
    Параметр db (data.db) не подходит — таблицы User там нет.
    """
    if not teacher_name:
        return None

    cleaned = clean_teacher_name(teacher_name)

    async with AuthSessionLocal() as auth_db:
        result = await auth_db.execute(select(User))
        users = result.scalars().all()

        # Сначала точное совпадение по всем пользователям
        for u in users:
            if names_match(u.full_name, cleaned):
                return u

        # Затем по username (иногда username = фамилия)
        surname = extract_surname(cleaned)
        if surname:
            for u in users:
                if surname in normalize_fio(u.username):
                    return u

    return None


async def get_all_teachers(db: AsyncSession) -> list[User]:
    """Возвращает всех активных преподавателей (из auth.db)."""
    async with AuthSessionLocal() as auth_db:
        result = await auth_db.execute(
            select(User).where(User.role == UserRole.TEACHER, User.is_active == True)
        )
        return list(result.scalars().all())


# ── Разбор намерения из сообщения пользователя ──────────────

ALL_MARKERS = [
    "всем преподавател", "всем преподам", "всем учителям", "всем педагогам",
    "все преподаватели", "всех преподавателей", "всех преподам", "всех учителей",
    "каждому преподавателю", "каждому учителю", "по всем преподавателям",
    "распредели всем", "распределить всем", "раздай всем", "раздать всем",
    "добавь всем", "добавить всем", "проставь всем", "проставить всем",
    "занеси всем", "внеси всем", "разложи по преподавателям", "разложить по преподавателям",
    "распредели по преподавателям", "распределить по преподавателям",
    "по всем учителям", "на всех преподавателей",
    "добавь каждому", "добавить каждому", "проставь каждому",
    # «в календарь (другого/другим/всем) преподавател...» — то же распределение,
    # но с упоминанием календаря. Формулировка без конкретного ФИО.
    "календарь другого преподавателя", "календарь других преподавателей",
    "календарь другим преподавателям", "календарь другому преподавателю",
    "календарь всех преподавателей", "календарь всем преподавателям",
    "календари преподавателей", "календарям преподавателей",
    "всем в календари", "каждому в календарь", "разложи по календарям",
    "расписание по календарям", "по преподавателям", "по всем преподавателям",
]


def detect_distribute_all(message: str) -> bool:
    """Определяет, просит ли пользователь распределить расписание всем."""
    if not message:
        return False
    m = message.lower().replace("ё", "е")
    return any(marker.replace("ё", "е") in m for marker in ALL_MARKERS)


# «перенеси ... в календарь Гавриловой» — перенос пар ОДНОГО преподавателя
# в ЕГО собственный календарь (а не в календарь загрузившего).
_TRANSFER_RE = re.compile(
    r"(?:в|на)\s+календар[а-яё]*\s+"
    r"(?:преподавателя\s+|учителя\s+|коллеги\s+)?"
    r"([А-ЯЁ][а-яё]{2,}(?:\s+[А-ЯЁ]\.\s*[А-ЯЁ]?\.?)?)"
)

# Слова, после «в календарь» означающие не конкретного человека
_TRANSFER_SKIP = {
    "своему", "свой", "свою", "своё", "мне", "себе", "мой", "моему",
    "другого", "другим", "другому", "всем", "каждому", "преподавателям",
    "учителям", "расписанию", "урок", "занятий", "пар", "файла", "преподавателю",
}


def detect_transfer_target(message: str, fallback_name: str = "") -> str:
    """Имя после «в календарь <Кому>», если это конкретный человек, иначе ''.

    «перенеси пары Чёрненковой в ЕЁ календарь» — имя берётся из fallback_name
    (экстрагированного из той же фразы), если после «в календарь» стоит
    притяжательное местоимение.
    """
    if not message:
        return ""
    m = _TRANSFER_RE.search(message)
    if m:
        name = m.group(1).strip()
        if name.lower().replace("ё", "е") in {s.replace("ё", "е") for s in _TRANSFER_SKIP}:
            return ""
        return name
    # «в его / в её / в их календарь» — целевой преподаватель назван ранее во фразе
    if fallback_name and re.search(r"(?:в|на)\s+(?:его|е[ёе]|их)\s+календар", message, re.IGNORECASE):
        return fallback_name
    return ""


# Известные роли/слова, которые не являются ФИО
STOP_WORDS = {
    "добавь", "добавить", "пары", "пара", "расписание", "календарь",
    "мое", "мои", "мне", "себе", "в", "и", "на", "все", "всем",
    "преподаватель", "преподавателя", "преподавателю", "учитель",
    "занятия", "занятие", "лекции", "загрузи", "поставь", "проставь",
    "учебный", "план", "группа", "группы", "число", "день", "года",
    "перенеси", "перенесите", "перенести", "перенес", "перенёс",
    "перекинь", "перекиньте", "перенаправь", "занеси", "внеси",
    "очисти", "очистить", "удали", "удалить", "полностью",
}


def extract_target_teacher(message: str) -> str:
    """Пытается извлечь ФИО преподавателя из текста запроса.
    Возвращает пустую строку, если явного ФИО нет.
    """
    if not message:
        return ""

    # Ищем шаблон «Фамилия И.О.» или «Фамилия Имя Отчество»
    # Паттерн 1: Фамилия И.О.
    m = re.search(r"([А-ЯЁ][а-яё]{3,})\s+([А-ЯЁ]\.\s?[А-ЯЁ]?\.?)", message)
    if m:
        return f"{m.group(1)} {m.group(2)}".replace(" ", " ").strip()

    # Паттерн 2: Фамилия Имя Отчество (три слова с большой буквы)
    m = re.search(r"([А-ЯЁ][а-яё]{3,})\s+([А-ЯЁ][а-яё]{2,})\s+([А-ЯЁ][а-яё]{3,})", message)
    if m:
        return m.group(0)

    # Паттерн 3: одиночная фамилия с заглавной буквы, не стоп-слово
    words = re.findall(r"\b([А-ЯЁ][а-яё]{3,})\b", message)
    for w in words:
        if w.lower() not in STOP_WORDS:
            return w

    return ""