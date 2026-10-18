"""Подключение к БД: асинхронный движок, фабрика сессий, базовый класс моделей."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(settings.database_url, echo=settings.sql_echo)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    """Базовый класс для всех ORM-моделей."""


async def get_session() -> AsyncIterator[AsyncSession]:
    """Зависимость FastAPI: отдаёт сессию на время запроса и закрывает её после."""
    async with SessionLocal() as session:
        yield session
