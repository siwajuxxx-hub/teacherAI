from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    # Приложение
    APP_NAME: str = "AI TEACHER (СФ МЭИ)"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # Базы данных
    AUTH_DB_PATH: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "auth.db")
    DATA_DB_PATH: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "data.db")

    # JWT
    JWT_SECRET: str = "change-me-in-production-use-a-strong-random-secret"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # AI (значения по умолчанию, меняются через админ-панель)
    AI_PROVIDER: str = "openrouter"
    AI_API_KEY: str = ""
    AI_MODEL: str = "google/gemini-2.0-flash-001"
    AI_BASE_URL: Optional[str] = None  # Для кастомных эндпоинтов

    # Шифрование API-ключа в БД
    ENCRYPTION_KEY: str = "change-me-32-bytes-key-for-aes!"

    # CORS
    CORS_ORIGINS: list = ["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"]

    # Загрузка файлов
    MAX_UPLOAD_SIZE_MB: int = 10
    ALLOWED_UPLOAD_EXTENSIONS: list = [".pdf", ".docx", ".doc", ".txt", ".png", ".jpg", ".jpeg", ".xls", ".xlsx"]

    # Медиа для новостей (картинки). Отдаётся как StaticFiles на /media.
    MEDIA_DIR: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "media")
    NEWS_MAX_IMAGES: int = 5
    NEWS_MAX_IMAGE_MB: int = 5

    # Статический фронтенд (собранный Vite dist). Если каталог существует —
    # FastAPI отдаёт его как SPA на том же origin, что и /api (для одного контейнера).
    STATIC_DIR: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()