"""Хранилище картинок новостей: валидация, запись, драфты, удаление.

Файлы живут в settings.MEDIA_DIR:
  news/<news_id>/<uuid>.<ext>        — опубликованные
  news_drafts/<draft_id>/<uuid>.<ext>— временные (карточка новости из чата ждёт решения)
Отдаются наружу маунтом /media в main.py (неугадываемые uuid-имена).
"""
from __future__ import annotations

import os
import re
import shutil
import uuid

from app.config import settings

NEWS_SUB = "news"
DRAFT_SUB = "news_drafts"
MAX_IMAGES = settings.NEWS_MAX_IMAGES
MAX_IMAGE_BYTES = settings.NEWS_MAX_IMAGE_MB * 1024 * 1024

# сигнатуры → расширение
_SIGNATURES: list[tuple[bytes, bytes | None, str]] = [
    (b"\x89PNG\r\n\x1a\n", None, ".png"),
    (b"\xff\xd8\xff", None, ".jpg"),
    (b"GIF87a", None, ".gif"),
    (b"GIF89a", None, ".gif"),
    (b"RIFF", b"WEBP", ".webp"),  # WEBP на смещении 8..12
]
_SAVED_NAME_RE = re.compile(r"^[0-9a-f]{32}\.(png|jpg|jpeg|gif|webp)$")


def _root() -> str:
    os.makedirs(settings.MEDIA_DIR, exist_ok=True)
    return settings.MEDIA_DIR


def detect_image(data: bytes) -> str | None:
    """Расширение по магическим байтам или None, если это не картинка."""
    for magic, tail, ext in _SIGNATURES:
        if data.startswith(magic):
            if tail and data[8:12] != tail:
                continue
            return ext
    return None


def validate_image(data: bytes, original_name: str = "") -> tuple[str, bytes]:
    """Проверка картинки. Возвращает (ext, data). Бросает ValueError с текстом для пользователя."""
    if not data:
        raise ValueError(f"Файл «{original_name}» пуст")
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError(f"Картинка «{original_name}» больше {settings.NEWS_MAX_IMAGE_MB} МБ")
    ext = detect_image(data)
    if not ext:
        raise ValueError(f"«{original_name}» — не картинка (принимаются PNG/JPG/GIF/WebP)")
    return ext, data


def store_image(data: bytes, ext: str, folder: str) -> str:
    name = f"{uuid.uuid4().hex}{ext}"
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, name), "wb") as f:
        f.write(data)
    return name


def news_folder(news_id: str) -> str:
    return os.path.join(_root(), NEWS_SUB, news_id)


def draft_folder(draft_id: str) -> str:
    return os.path.join(_root(), DRAFT_SUB, draft_id)


def new_draft_id() -> str:
    return uuid.uuid4().hex


def save_draft_images(draft_id: str, files: list[tuple[bytes, str]]) -> list[str]:
    """files — список (bytes, original_name). Все или ничего: при ошибке черновик не создаётся."""
    if len(files) > MAX_IMAGES:
        raise ValueError(f"Можно приложить максимум {MAX_IMAGES} картинок")
    folder = draft_folder(draft_id)
    if os.path.isdir(folder):
        shutil.rmtree(folder, ignore_errors=True)
    saved: list[str] = []
    try:
        for data, name in files:
            ext, data = validate_image(data, name)
            saved.append(store_image(data, ext, folder))
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return saved


def move_draft_to_news(draft_id: str, news_id: str, names: list[str]) -> list[str]:
    src = draft_folder(draft_id)
    dst = news_folder(news_id)
    moved: list[str] = []
    if not os.path.isdir(src):
        return moved
    os.makedirs(dst, exist_ok=True)
    for n in names:
        safe = safe_name(n)
        p = os.path.join(src, safe)
        if safe and os.path.isfile(p):
            shutil.move(p, os.path.join(dst, safe))
            moved.append(safe)
    shutil.rmtree(src, ignore_errors=True)
    return moved


def delete_news_images(news_id: str) -> None:
    shutil.rmtree(news_folder(news_id), ignore_errors=True)


def delete_draft(draft_id: str) -> None:
    shutil.rmtree(draft_folder(draft_id), ignore_errors=True)


def prune_orphan_drafts(max_age_s: int = 3 * 3600) -> None:
    """Старые неподтверждённые черновики чистим (вызывается лениво при создании new draft)."""
    base = os.path.join(_root(), DRAFT_SUB)
    if not os.path.isdir(base):
        return
    import time
    now = time.time()
    for d in os.listdir(base):
        p = os.path.join(base, d)
        try:
            if os.path.isdir(p) and now - os.path.getmtime(p) > max_age_s:
                shutil.rmtree(p, ignore_errors=True)
        except OSError:
            pass


def safe_name(name: str) -> str:
    """Только наши uuid-имена;anything else — None (защита от path traversal)."""
    name = os.path.basename(name or "")
    return name if _SAVED_NAME_RE.match(name) else ""


def image_url(news_id: str, name: str) -> str:
    return f"/media/{NEWS_SUB}/{news_id}/{name}"


def draft_url(draft_id: str, name: str) -> str:
    return f"/media/{DRAFT_SUB}/{draft_id}/{name}"


def read_file_for_serving(news_id: str, name: str) -> str | None:
    safe = safe_name(name)
    if not safe:
        return None
    p = os.path.join(news_folder(news_id), safe)
    return p if os.path.isfile(p) else None
