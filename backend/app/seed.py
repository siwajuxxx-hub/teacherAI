"""Создание начальных данных: admin/admin и настройки по умолчанию."""
import asyncio
from app.database import init_databases, AuthSessionLocal
from app.models.auth_models import User, UserRole, AppSetting
from app.security import hash_password, encrypt_api_key
from sqlalchemy import select


async def seed():
    await init_databases()
    async with AuthSessionLocal() as session:
        # Проверим, есть ли уже admin
        result = await session.execute(select(User).where(User.username == "admin"))
        if not result.scalar_one_or_none():
            admin = User(
                username="admin",
                password_hash=hash_password("admin"),
                full_name="Администратор",
                position="Администратор системы",
                role=UserRole.ADMIN,
            )
            session.add(admin)

            # Демо-управляющий
            manager = User(
                username="manager",
                password_hash=hash_password("manager"),
                full_name="Иван Петрович",
                position="Завуч",
                role=UserRole.MANAGER,
            )
            session.add(manager)

            # Демо-преподаватель
            teacher = User(
                username="teacher",
                password_hash=hash_password("teacher"),
                full_name="Мария Ивановна",
                position="Преподаватель математики",
                role=UserRole.TEACHER,
            )
            session.add(teacher)

            # Демо-преподаватель Гаврилов (для теста расписания)
            gavrilov = User(
                username="gavrilov",
                password_hash=hash_password("gavrilov"),
                full_name="Гаврилов А.И.",
                position="Преподаватель информатики",
                role=UserRole.TEACHER,
            )
            session.add(gavrilov)

            # Настройки AI по умолчанию
            default_settings = [
                AppSetting(key="ai_provider", value="openrouter"),
                AppSetting(key="ai_api_key", value=encrypt_api_key("")),
                AppSetting(key="ai_model", value="google/gemini-2.0-flash-001"),
                AppSetting(key="ai_base_url", value=""),
            ]
            session.add_all(default_settings)

            await session.commit()
            print("✅ Начальные данные созданы: admin/admin, manager/manager, teacher/teacher")
        else:
            print("ℹ️  Администратор уже существует, пропускаем сидирование")


if __name__ == "__main__":
    asyncio.run(seed())