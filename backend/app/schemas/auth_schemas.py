from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from app.models.auth_models import UserRole


# --- Auth ---

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: str
    username: str
    full_name: str
    position: str
    role: UserRole
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=4, max_length=100)
    full_name: str = Field(default="", max_length=255)
    position: str = Field(default="", max_length=255)
    role: UserRole = UserRole.TEACHER


class UserUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=2, max_length=100)
    full_name: Optional[str] = Field(None, max_length=255)
    position: Optional[str] = Field(None, max_length=255)
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class PasswordChange(BaseModel):
    password: str = Field(min_length=4, max_length=100)


# --- Settings ---

class AISettingsUpdate(BaseModel):
    provider: str = "openrouter"  # openrouter, openai, gemini
    api_key: str = ""
    model: str = "google/gemini-2.0-flash-001"
    base_url: Optional[str] = None


class AISettingsOut(BaseModel):
    provider: str
    model: str
    base_url: Optional[str] = None
    has_api_key: bool = False  # Не отдаём ключ, только флаг наличия


# --- Keepalive (имитация активности против сна free-хостинга) ---

class KeepaliveUpdate(BaseModel):
    enabled: bool


class KeepaliveOut(BaseModel):
    enabled: bool
    target: str
    interval_sec: int
    pings_ok: int
    pings_failed: int
    last_ok_at: Optional[str] = None
    last_error: Optional[str] = None
    external_url_mode: bool = False