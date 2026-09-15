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