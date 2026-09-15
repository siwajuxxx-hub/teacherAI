"""Keepalive — лёгкая имитация активности против sleep free-инстанса Render.

Как это работает на Render:
- Free web service засыпает, если на его ПУБЛИЧНЫЙ адрес (через edge-прокси
  Render) ~15 минут не приходит ни одного запроса.
- Запрос в localhost внутри контейдера edge не проходит и НЕ засчитывается.
- Поэтому сервис пингует САМ СЕБЯ по внешнему URL из переменной окружения
  RENDER_EXTERNAL_URL (Render задаёт её автоматически): запрос уходит наружу,
  возвращается через edge и засчитывается как входящая активность.
- Вне Render (локально/локальный Docker) внешнего URL нет — пингуем
  127.0.0.1, чтобы механизм оставался видимым и тестируемым (это безопасно:
  трафик не покидает машину).

Активность совсем небольшая: один GET /api/health раз в KEEPALIVE_INTERVAL_SEC
секунд (по умолчанию 240). Флаг вкл/выкл хранится в AppSetting["keepalive_enabled"]
(значение "true"/"false"), переключается из админ-панели без перезапуска:
цикл перечитывает настройку перед каждым пингом.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone

import httpx
from sqlalchemy import select

logger = logging.getLogger("keepalive")

INTERVAL_SEC = int(os.environ.get("KEEPALIVE_INTERVAL_SEC", "240"))
PORT = os.environ.get("PORT", "8000")
PING_PATH = "/api/health"


def ping_target() -> str:
    external = (os.environ.get("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")
    if external:
        return external + PING_PATH
    return f"http://127.0.0.1:{PORT}{PING_PATH}"


class KeepaliveService:
    def __init__(self) -> None:
        self.pings_ok = 0
        self.pings_failed = 0
        self.last_ok_at: datetime | None = None
        self.last_error: str | None = None
        self._task: asyncio.Task | None = None

    async def _is_enabled(self) -> bool:
        # Импорты внутри: модуль грузится раньше БД, аCircular imports тут ни к чему.
        from app.database import AuthSessionLocal
        from app.models.auth_models import AppSetting

        async with AuthSessionLocal() as session:
            row = (
                await session.execute(
                    select(AppSetting).where(AppSetting.key == "keepalive_enabled")
                )
            ).scalar_one_or_none()
        # Ключа ещё нет (свежий деплой) — по умолчанию включено.
        return True if row is None else row.value.strip().lower() == "true"

    async def _ping_once(self) -> None:
        url = ping_target()
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url)
            if resp.status_code == 200:
                self.pings_ok += 1
                self.last_ok_at = datetime.now(timezone.utc)
                self.last_error = None
            else:
                self.pings_failed += 1
                self.last_error = f"HTTP {resp.status_code}"
                logger.warning("keepalive: %s вернул %s", url, resp.status_code)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — фоновый цикл не должен умирать
            self.pings_failed += 1
            self.last_error = f"{type(exc).__name__}: {exc}"
            logger.warning("keepalive: пинг %s не удался: %s", url, exc)

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(INTERVAL_SEC)
            try:
                if await self._is_enabled():
                    await self._ping_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.error("keepalive: сбой цикла (%s), продолжаем", exc)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())
            logger.info(
                "keepalive запущен: цель %s, интервал %d сек", ping_target(), INTERVAL_SEC
            )

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._task = None

    def status(self) -> dict:
        # enabled сюда не включаем — его читает роутер из БД (свежее значение).
        return {
            "target": ping_target(),
            "interval_sec": INTERVAL_SEC,
            "pings_ok": self.pings_ok,
            "pings_failed": self.pings_failed,
            "last_ok_at": self.last_ok_at.isoformat() if self.last_ok_at else None,
            "last_error": self.last_error,
            "external_url_mode": bool((os.environ.get("RENDER_EXTERNAL_URL") or "").strip()),
        }


keepalive = KeepaliveService()
