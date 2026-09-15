import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy import select, func

from app.config import settings
from app.database import init_databases, AuthSessionLocal


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_databases()

    # Пустая база (свежий деплой) — сидируем демо-данными, чтобы демо работало
    # сразу: admin/admin, manager/manager, teacher/teacher.
    from app.models.auth_models import User
    async with AuthSessionLocal() as session:
        users = (await session.execute(select(func.count()).select_from(User))).scalar()
    if not users:
        from app.seed import seed
        await seed()

    # Фоновый keepalive против сна free-инстанса Render (управляется из админки)
    from app.services.keepalive import keepalive
    keepalive.start()

    yield
    # Shutdown
    await keepalive.stop()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем роутеры
# ВАЖНО: роутер settings импортируем с алиасом, иначе он перекрывает
# объект конфигурации `settings` из app.config.
from app.routers import auth, schedule, tasks, chat, stats, news
from app.routers import settings as settings_router
app.include_router(auth.router)
app.include_router(auth.users_router)
app.include_router(schedule.router)
app.include_router(tasks.router)
app.include_router(chat.router)
app.include_router(settings_router.router)
app.include_router(stats.router)
app.include_router(news.router)

# Картинки новостей (и временные драфты карточек из чата) — /media/news/...
# Монтируем независимо от того, собран ли SPA.
os.makedirs(settings.MEDIA_DIR, exist_ok=True)
app.mount("/media", StaticFiles(directory=settings.MEDIA_DIR), name="media")


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": settings.APP_VERSION}


# ─── Статический фронтенд (режим одного контейнера) ────────────────
# Если рядом лежит собранный Vite-dist — отдаём SPA с того же origin,
# что и API: ни CORS, ни отдельного хостинга для фронта не нужно.

def _mount_frontend(application: FastAPI) -> bool:
    static_dir = settings.STATIC_DIR
    if not static_dir or not os.path.isdir(static_dir):
        return False
    index_html = os.path.join(static_dir, "index.html")
    if not os.path.isfile(index_html):
        return False

    assets_dir = os.path.join(static_dir, "assets")
    if os.path.isdir(assets_dir):
        application.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    root = os.path.realpath(static_dir)

    @application.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        # API-маршруты сюда попадать не должны — чужие пути возвращаем 404 JSON
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        if full_path:
            candidate = os.path.realpath(os.path.join(static_dir, full_path))
            # защита от path traversal
            if candidate.startswith(root) and os.path.isfile(candidate):
                return FileResponse(candidate)
        return FileResponse(index_html)

    return True


FRONTEND_MOUNTED = _mount_frontend(app)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
