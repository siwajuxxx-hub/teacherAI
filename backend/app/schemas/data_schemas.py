from pydantic import BaseModel, Field
from typing import Optional
from datetime import date, time, datetime
from app.models.data_models import (
    ScheduleType, ScheduleSource, TaskPriority, TaskStatus, TaskScope,
)


# --- Расписание ---

class ScheduleCreate(BaseModel):
    user_id: Optional[str] = None  # Если None — берётся текущий пользователь
    title: str = Field(min_length=1, max_length=500)
    day_of_week: int = Field(ge=0, le=6)  # 0=Пн ... 6=Вс
    start_time: str  # HH:MM
    end_time: str    # HH:MM
    group_name: str = ""
    room: str = ""
    type: ScheduleType = ScheduleType.LESSON
    source: ScheduleSource = ScheduleSource.MANUAL


class ScheduleBatchCreate(BaseModel):
    """Массовое добавление записей расписания после AI-парсинга."""
    user_id: Optional[str] = None
    items: list[ScheduleCreate]


class ScheduleUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=500)
    day_of_week: Optional[int] = Field(None, ge=0, le=6)
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    group_name: Optional[str] = None
    room: Optional[str] = None
    type: Optional[ScheduleType] = None


class ScheduleOut(BaseModel):
    id: str
    user_id: str
    title: str
    day_of_week: int
    start_time: str
    end_time: str
    group_name: str
    room: str
    type: ScheduleType
    source: ScheduleSource
    created_by: str
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Задачи ---

class TaskCreate(BaseModel):
    user_id: Optional[str] = None  # Если None — текущий пользователь
    title: str = Field(min_length=1, max_length=500)
    description: str = ""
    # Период задачи: day (due_date), month (due_month), year (due_year), none
    scope: TaskScope = TaskScope.NONE
    due_date: Optional[str] = None    # YYYY-MM-DD
    due_month: Optional[str] = None   # YYYY-MM
    due_year: Optional[int] = None    # YYYY
    status: TaskStatus = TaskStatus.PENDING


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=500)
    description: Optional[str] = None
    scope: Optional[TaskScope] = None
    due_date: Optional[str] = None
    due_month: Optional[str] = None
    due_year: Optional[int] = None


class TaskStatusUpdate(BaseModel):
    status: TaskStatus


class TaskOut(BaseModel):
    id: str
    user_id: str
    title: str
    description: str
    status: TaskStatus
    scope: TaskScope = TaskScope.NONE
    due_date: Optional[str] = None
    due_month: Optional[str] = None
    due_year: Optional[int] = None
    completed_at: Optional[datetime] = None
    assigned_by: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Чат ---

class ChatMessageRequest(BaseModel):
    message: str


class ChatMessageOut(BaseModel):
    id: str
    role: str
    content: str
    context_type: Optional[str] = None
    context_id: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ScheduleParsedOut(BaseModel):
    """Результат AI-парсинга расписания."""
    items: list[ScheduleCreate]
    raw_text: str