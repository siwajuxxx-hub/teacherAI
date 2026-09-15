"""Лента новостей: читают все, публикуют/правят — только manager и admin."""
from __future__ import annotations

import json
import os
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_data_session
from app.models.auth_models import User
from app.models.data_models import NewsItem, NewsRead
from app.security import get_current_user, require_admin_or_manager
from app.services import news_store

router = APIRouter(prefix="/api/news", tags=["Новости"])


def _pub(n: NewsItem) -> dict:
    try:
        imgs = json.loads(n.images_json or "[]")
    except json.JSONDecodeError:
        imgs = []
    return {
        "id": n.id,
        "title": n.title,
        "body": n.body,
        "pinned": bool(n.pinned),
        "author_name": n.author_name,
        "created_at": n.created_at.isoformat() if n.created_at else "",
        "updated_at": n.updated_at.isoformat() if n.updated_at else "",
        "images": [news_store.image_url(n.id, i) for i in imgs if news_store.safe_name(i)],
    }


def _pin_flag(v: str | None) -> int:
    return 1 if (v or "").strip().lower() in ("true", "1", "да", "on") else 0


async def _get_or_404(db: AsyncSession, news_id: str) -> NewsItem:
    n = (await db.execute(select(NewsItem).where(NewsItem.id == news_id))).scalar_one_or_none()
    if n is None:
        raise HTTPException(404, detail="Новость не найдена")
    return n


async def _read_images(files: list[UploadFile]) -> list[tuple[bytes, str]]:
    out = []
    for f in files or []:
        data = await f.read()
        if not data and not (f.filename or ""):
            continue
        out.append((data, f.filename or "картинка"))
    return out


@router.get("")
async def news_list(
    limit: int = 100,
    db: AsyncSession = Depends(get_data_session),
    _: User = Depends(get_current_user),
):
    r = await db.execute(
        select(NewsItem).order_by(NewsItem.pinned.desc(), NewsItem.created_at.desc())
        .limit(max(1, min(limit, 500))))
    return {"items": [_pub(n) for n in r.scalars().all()]}


@router.get("/unread")
async def news_unread(
    db: AsyncSession = Depends(get_data_session),
    current_user: User = Depends(get_current_user),
):
    from sqlalchemy import func
    last = (await db.execute(
        select(NewsRead.last_read_at).where(NewsRead.user_id == current_user.id)
    )).scalar_one_or_none()
    q = select(func.count()).select_from(NewsItem)
    if last is not None:
        q = q.where(NewsItem.created_at > last)
    return {"count": (await db.execute(q)).scalar() or 0}


@router.post("/read")
async def news_read_mark(
    db: AsyncSession = Depends(get_data_session),
    current_user: User = Depends(get_current_user),
):
    row = (await db.execute(
        select(NewsRead).where(NewsRead.user_id == current_user.id)
    )).scalar_one_or_none()
    if row is None:
        db.add(NewsRead(user_id=current_user.id, last_read_at=datetime.utcnow()))
    else:
        row.last_read_at = datetime.utcnow()
    await db.commit()
    return {"ok": True}


@router.post("")
async def news_create(
    title: str = Form(""),
    body: str = Form(""),
    pinned: str = Form("false"),
    images: list[UploadFile] = File(default=[]),
    db: AsyncSession = Depends(get_data_session),
    current_user: User = Depends(require_admin_or_manager),
):
    title, body = title.strip()[:200], body.strip()[:20000]
    if not title and not body:
        raise HTTPException(400, detail="Новость не может быть пустой")
    pairs = await _read_images(images)
    if len(pairs) > news_store.MAX_IMAGES:
        raise HTTPException(400, detail=f"Можно приложить максимум {news_store.MAX_IMAGES} картинок")

    n = NewsItem(title=title, body=body, pinned=_pin_flag(pinned),
                 author_id=current_user.id, author_name=current_user.full_name)
    db.add(n)
    await db.flush()
    try:
        names = _store_into_news(n.id, pairs)
    except ValueError as e:
        await db.delete(n)
        await db.commit()
        raise HTTPException(400, detail=str(e))
    n.images_json = json.dumps(names, ensure_ascii=False)
    await db.commit()
    return _pub(n)


def _store_into_news(news_id: str, pairs: list[tuple[bytes, str]]) -> list[str]:
    folder = news_store.news_folder(news_id)
    os.makedirs(folder, exist_ok=True)
    names = []
    saved = []
    try:
        for data, orig in pairs:
            ext, data = news_store.validate_image(data, orig)
            saved.append(news_store.store_image(data, ext, folder))
        return saved
    except Exception:
        for s in saved:
            try:
                os.remove(os.path.join(folder, s))
            except OSError:
                pass
        raise


@router.put("/{news_id}")
async def news_update(
    news_id: str,
    title: str | None = Form(None),
    body: str | None = Form(None),
    pinned: str | None = Form(None),
    keep_images: str | None = Form(None),
    images: list[UploadFile] = File(default=[]),
    db: AsyncSession = Depends(get_data_session),
    current_user: User = Depends(require_admin_or_manager),
):
    n = await _get_or_404(db, news_id)
    if title is not None:
        n.title = title.strip()[:200]
    if body is not None:
        n.body = body.strip()[:20000]
    if pinned is not None:
        n.pinned = _pin_flag(pinned)
    if not n.title.strip() and not n.body.strip():
        raise HTTPException(400, detail="Новость не может быть пустой")
    try:
        cur = json.loads(n.images_json or "[]")
    except json.JSONDecodeError:
        cur = []
    new_pairs = await _read_images(images)

    if keep_images is not None:  # клиент явно прислал список оставляемых
        try:
            keep = [i for i in json.loads(keep_images) if i in cur and news_store.safe_name(i)]
        except json.JSONDecodeError:
            raise HTTPException(400, detail="keep_images — JSON-список имён")
    else:
        keep = cur  # без keep_images существующие картинки сохраняются
    if len(keep) + len(new_pairs) > news_store.MAX_IMAGES:
        raise HTTPException(400, detail=f"Всего картинок не больше {news_store.MAX_IMAGES}")

    # удалить то, что не оставили
    folder = news_store.news_folder(n.id)
    for stale in set(cur) - set(keep):
        safe = news_store.safe_name(stale)
        if safe and os.path.isfile(os.path.join(folder, safe)):
            try:
                os.remove(os.path.join(folder, safe))
            except OSError:
                pass
    added: list[str] = []
    if new_pairs:
        try:
            added = _store_into_news(n.id, new_pairs)
        except ValueError as e:
            raise HTTPException(400, detail=str(e))
    n.images_json = json.dumps(keep + added, ensure_ascii=False)
    await db.commit()
    return _pub(n)


@router.patch("/{news_id}/pin")
async def news_pin(
    news_id: str,
    db: AsyncSession = Depends(get_data_session),
    _: User = Depends(require_admin_or_manager),
):
    n = await _get_or_404(db, news_id)
    n.pinned = 0 if n.pinned else 1
    await db.commit()
    return _pub(n)


@router.delete("/{news_id}")
async def news_delete(
    news_id: str,
    db: AsyncSession = Depends(get_data_session),
    _: User = Depends(require_admin_or_manager),
):
    n = await _get_or_404(db, news_id)
    news_store.delete_news_images(n.id)
    await db.delete(n)
    await db.commit()
    return {"ok": True}
