import uuid
from datetime import datetime, date, time
from sqlalchemy import String, Integer, DateTime, Date, Time, Enum as SAEnum, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
import enum


class ScheduleType(str, enum.Enum):
    LESSON = "lesson"
    MEETING = "meeting"
    OTHER = "other"


class ScheduleSource(str, enum.Enum):
    MANUAL = "manual"
    PDF_IMPORT = "pdf_import"
    MANAGER = "manager"


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)  # 0=Пн ... 6=Вс
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    group_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    room: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    type: Mapped[ScheduleType] = mapped_column(SAEnum(ScheduleType), nullable=False, default=ScheduleType.LESSON)
    source: Mapped[ScheduleSource] = mapped_column(SAEnum(ScheduleSource), nullable=False, default=ScheduleSource.MANUAL)
    # Конкретная дата занятия. NULL = недельный ШАБЛОН (повторяется каждую
    # неделю, пока действует); непустое = занятие ровно на этот день.
    event_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    # Только для шаблонов: фильтр по номерам недель семестра.
    # 'odd' (верх/чётные ISO), 'even' (низ/нечётные) или список '3,7,11';
    # NULL = любая неделя.
    weeks: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_by: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TaskPriority(str, enum.Enum):
    """Оставлено для совместимости со старыми записями в БД."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TaskScope(str, enum.Enum):
    """На какой период ставится задача."""
    DAY = "day"        # конкретный день (due_date)
    MONTH = "month"    # месяц (due_month, напр. 2026-09)
    YEAR = "year"      # год (due_year, напр. 2026)
    NONE = "none"      # без срока
    # Устаревшие значения — только для чтения старых записей
    WEEK = "week"


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    OVERDUE = "overdue"


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Приоритет больше не используется в интерфейсе, но колонка сохранена
    # (nullable), чтобы не ломать существующие базы данных.
    priority: Mapped[TaskPriority | None] = mapped_column(SAEnum(TaskPriority), nullable=True)
    status: Mapped[TaskStatus] = mapped_column(SAEnum(TaskStatus), nullable=False, default=TaskStatus.PENDING)
    scope: Mapped[TaskScope] = mapped_column(
        SAEnum(TaskScope), nullable=False, default=TaskScope.NONE, server_default="NONE"
    )
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Период: месяц (YYYY-MM) или год (YYYY)
    due_month: Mapped[str | None] = mapped_column(String(7), nullable=True)
    due_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    assigned_by: Mapped[str | None] = mapped_column(String(36), nullable=True)  # Кто поставил задачу
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ChatHistory(Base):
    __tablename__ = "chat_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user, assistant, system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    context_type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # chat, schedule, task
    context_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LastImport(Base):
    """Устарела: заменена ScheduleImport. Таблица и данные сохранены для отката.

    Сохраняет распарсенные items, чтобы текстовые запросы («перенеси пары Федуловой
    ко мне», «распредели всем») исполнялись детерминированно, без повторного
    прикрепления файла и без AI-фантазий.
    """
    __tablename__ = "last_imports"

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    filename: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    items_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")


class ImportKind(str, enum.Enum):
    WEEKLY = "weekly"   # сетка дней недели (xls-шаблон МЭИ)
    DATED = "dated"     # занятия на конкретные даты (сессия, docx/календарь)


class ImportState(str, enum.Enum):
    ASK_PERIOD = "ask_period"  # ждём ответ: неделя или семестр?
    ASK_END = "ask_end"        # выбрали семестр — ждём дату окончания
    READY = "ready"            # items развёрнуты/готовы, ждут карточки-подтверждения
    APPLIED = "applied"        # подтверждено и записано
    CANCELLED = "cancelled"


class ScheduleImport(Base):
    """Один распознанный файл расписания с машиной состояний импорта."""
    __tablename__ = "schedule_imports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)  # кто загрузил
    filename: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    kind: Mapped[ImportKind] = mapped_column(SAEnum(ImportKind), nullable=False)
    state: Mapped[ImportState] = mapped_column(
        SAEnum(ImportState), nullable=False, default=ImportState.ASK_PERIOD,
        server_default="ASK_PERIOD",
    )
    items_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    # Исходные распознанные занятия (до развёртки по датам) — чтобы «передумать»
    # период и развернуть заново было из чего.
    source_items_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    # Отложенное требование к импорту из сообщения-загрузки:
    # {"mode": "self|transfer|distribute", "fio": "..."} — применить при READY
    pending_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # Границы развёртки weekly-шаблона: понедельник недели-1 и последнее занятие
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ProposalKind(str, enum.Enum):
    IMPORT_PLAN = "import_plan"  # «занести вот эти пары» (массовый импорт)
    ACTIONS = "actions"          # набор точечных действий AI/намерений
    CLEAR = "clear"              # очистка календаря (диапазон/день/всё)


class ProposalStatus(str, enum.Enum):
    PENDING = "pending"
    APPLIED = "applied"
    REJECTED = "rejected"


class Proposal(Base):
    """Серверная память о предложенных операциях (карточки подтверждения).

    Клиент подтверждает по proposal_id; сырой список действий от клиента
    больше не принимается. kind='actions': payload = {"actions":[...]};
    kind='import_plan': payload = {"import_id", "rows":[...], "summary"};
    kind='clear': payload = {"selector", "ids":[...]}.
    """
    __tablename__ = "proposals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    kind: Mapped[ProposalKind] = mapped_column(SAEnum(ProposalKind), nullable=False)
    status: Mapped[ProposalStatus] = mapped_column(
        SAEnum(ProposalStatus), nullable=False, default=ProposalStatus.PENDING,
        server_default="PENDING",
    )
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)