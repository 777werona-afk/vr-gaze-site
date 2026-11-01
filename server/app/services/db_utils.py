"""Мелкие помощники для работы с БД в обработчиках."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.errors import ConflictError


async def commit_or_conflict(db: AsyncSession, message: str) -> None:
    """commit(); нарушение уникальности (в том числе из-за гонки запросов) -> 409."""
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ConflictError(message) from None
