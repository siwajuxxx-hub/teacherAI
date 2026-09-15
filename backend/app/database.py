from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings
import os

# Каталоги для SQLite-файлов (в свежем контейнере их ещё нет)
for _p in (settings.AUTH_DB_PATH, settings.DATA_DB_PATH):
    os.makedirs(os.path.dirname(_p), exist_ok=True)

# Два движка для двух баз данных
auth_engine = create_async_engine(
    f"sqlite+aiosqlite:///{settings.AUTH_DB_PATH}",
    echo=settings.DEBUG,
    connect_args={"check_same_thread": False}
)

data_engine = create_async_engine(
    f"sqlite+aiosqlite:///{settings.DATA_DB_PATH}",
    echo=settings.DEBUG,
    connect_args={"check_same_thread": False}
)

# Фабрики сессий
AuthSessionLocal = async_sessionmaker(auth_engine, class_=AsyncSession, expire_on_commit=False)
DataSessionLocal = async_sessionmaker(data_engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_auth_session() -> AsyncSession:
    async with AuthSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_data_session() -> AsyncSession:
    async with DataSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_databases():
    """Создать все таблицы при старте приложения."""
    from app.models.auth_models import Base as AuthBase
    from app.models.data_models import Base as DataBase

    async with auth_engine.begin() as conn:
        await conn.run_sync(AuthBase.metadata.create_all)

    async with data_engine.begin() as conn:
        await conn.run_sync(DataBase.metadata.create_all)

    await _migrate_tasks()


async def _migrate_tasks():
    """Лёгкие миграции таблицы tasks (SQLite не умеет ALTER через ORM).

    Добавляет новые колонки, снимает NOT NULL с priority и перестраивает
    таблицу при необходимости.
    """
    from sqlalchemy import text

    async with data_engine.begin() as conn:
        result = await conn.execute(text("PRAGMA table_info(tasks)"))
        rows = result.fetchall()
        columns = {row[1] for row in rows}

        if not columns:
            return  # таблицы ещё нет — create_all её создаст

        # priority больше не обязателен: перестраиваем таблицу, если NOT NULL
        priority_row = next((r for r in rows if r[1] == "priority"), None)
        priority_notnull = bool(priority_row and priority_row[3])

        additions = {
            "scope": "ALTER TABLE tasks ADD COLUMN scope VARCHAR(10) NOT NULL DEFAULT 'NONE'",
            "due_month": "ALTER TABLE tasks ADD COLUMN due_month VARCHAR(7)",
            "due_year": "ALTER TABLE tasks ADD COLUMN due_year INTEGER",
            "completed_at": "ALTER TABLE tasks ADD COLUMN completed_at DATETIME",
        }
        for name, ddl in additions.items():
            if name not in columns:
                await conn.execute(text(ddl))
                columns.add(name)

        # ВАЖНО: SQLAlchemy хранит Enum по ИМЕНИ члена (DAY), а не по значению (day).
        # Ранняя версия миграции писала строчные значения — приводим их к верхнему регистру.
        for col in ("scope", "status"):
            await conn.execute(text(
                f"UPDATE tasks SET {col} = UPPER({col}) "
                f"WHERE {col} IS NOT NULL AND {col} != UPPER({col})"
            ))
        # Старое значение 'WEEK' больше не используется — переводим в 'DAY'
        await conn.execute(text("UPDATE tasks SET scope = 'DAY' WHERE scope = 'WEEK'"))

        if priority_notnull:
            # Пересоздаём таблицу, чтобы priority стал NULL-совместимым
            await conn.execute(text("PRAGMA foreign_keys=off"))
            await conn.execute(text("""
                CREATE TABLE tasks_new (
                    id VARCHAR(36) NOT NULL PRIMARY KEY,
                    user_id VARCHAR(36) NOT NULL,
                    title VARCHAR(500) NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    priority VARCHAR(10),
                    status VARCHAR(11) NOT NULL DEFAULT 'PENDING',
                    scope VARCHAR(10) NOT NULL DEFAULT 'NONE',
                    due_date DATE,
                    due_month VARCHAR(7),
                    due_year INTEGER,
                    completed_at DATETIME,
                    assigned_by VARCHAR(36),
                    created_at DATETIME
                )
            """))
            await conn.execute(text("""
                INSERT INTO tasks_new
                    (id, user_id, title, description, priority, status, scope,
                     due_date, due_month, due_year, completed_at, assigned_by, created_at)
                SELECT id, user_id, title, description, priority, status,
                       COALESCE(scope, 'NONE'), due_date, due_month, due_year,
                       completed_at, assigned_by, created_at
                FROM tasks
            """))
            await conn.execute(text("DROP TABLE tasks"))
            await conn.execute(text("ALTER TABLE tasks_new RENAME TO tasks"))
            await conn.execute(text("PRAGMA foreign_keys=on"))

        # Определяем scope у старых записей по due_date
        await conn.execute(text(
            "UPDATE tasks SET scope = 'DAY' "
            "WHERE (scope IS NULL OR scope = 'NONE') AND due_date IS NOT NULL"
        ))

        # Отмечаем дату завершения у уже выполненных задач
        await conn.execute(text(
            "UPDATE tasks SET completed_at = created_at "
            "WHERE completed_at IS NULL AND status = 'DONE'"
        ))