"""Роутер настроек приложения (только admin)."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_auth_session
from app.models.auth_models import AppSetting, User
from app.schemas.auth_schemas import AISettingsUpdate, AISettingsOut
from app.security import require_admin, encrypt_api_key, decrypt_api_key

router = APIRouter(prefix="/api/settings", tags=["Настройки"])


@router.get("/", response_model=AISettingsOut)
async def get_settings(
    db: AsyncSession = Depends(get_auth_session),
    _: User = Depends(require_admin),
):
    result = await db.execute(select(AppSetting))
    rows = {r.key: r.value for r in result.scalars().all()}

    return AISettingsOut(
        provider=rows.get("ai_provider", "openrouter"),
        model=rows.get("ai_model", "google/gemini-2.0-flash-001"),
        base_url=rows.get("ai_base_url", "") or None,
        has_api_key=bool(decrypt_api_key(rows.get("ai_api_key", ""))),
    )


@router.put("/ai", response_model=AISettingsOut)
async def update_ai_settings(
    body: AISettingsUpdate,
    db: AsyncSession = Depends(get_auth_session),
    _: User = Depends(require_admin),
):
    # Загружаем текущие настройки
    result = await db.execute(select(AppSetting))
    existing = {r.key: r for r in result.scalars().all()}

    updates = {
        "ai_provider": body.provider,
        "ai_model": body.model,
        "ai_base_url": body.base_url or "",
    }

    for key, value in updates.items():
        if key in existing:
            existing[key].value = value
        else:
            db.add(AppSetting(key=key, value=value))

    # API-ключ обновляем только если передан непустой
    if body.api_key:
        encrypted = encrypt_api_key(body.api_key)
        if "ai_api_key" in existing:
            existing["ai_api_key"].value = encrypted
        else:
            db.add(AppSetting(key="ai_api_key", value=encrypted))

    await db.commit()

    return AISettingsOut(
        provider=body.provider,
        model=body.model,
        base_url=body.base_url or None,
        has_api_key=bool(body.api_key or ("ai_api_key" in existing and decrypt_api_key(existing["ai_api_key"].value))),
    )


@router.post("/ai/test")
async def test_ai_connection(
    db: AsyncSession = Depends(get_auth_session),
    _: User = Depends(require_admin),
):
    """Проверка подключения к AI-провайдеру."""
    import logging
    import traceback

    logger = logging.getLogger("ai_test")
    try:
        from app.services.ai_service import create_ai_provider

        provider = await create_ai_provider()
        full_response = ""
        async for chunk in provider.chat_stream(
            [{"role": "user", "content": "Скажи 'Тест подключения успешен' одним предложением."}],
            temperature=0.1,
        ):
            full_response += chunk

        if not full_response.strip():
            return {
                "status": "error",
                "error": "Провайдер вернул пустой ответ. Проверьте название модели и base_url.",
            }

        return {
            "status": "ok",
            "response": full_response[:200],
        }
    except Exception as e:
        logger.error("AI test failed:\n%s", traceback.format_exc())
        return {
            "status": "error",
            "error": f"{type(e).__name__}: {e}",
        }