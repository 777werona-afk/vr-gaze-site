"""Наполнение БД тестовыми данными (seed): группы, участники и экспонаты.

Запуск из папки server/ после миграций:

    python -m app.seed

Повторный запуск безопасен: уже существующие записи пропускаются (ON CONFLICT DO NOTHING).
Список экспонатов демонстрационный: замените его реальными экспонатами музея из Unity.
"""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal, engine
from app.models import Exhibit, Participant, ParticipantGroup

logger = logging.getLogger("app.seed")

# (название, описание, контрольная ли группа)
GROUPS = [
    ("Нарушения моторики", "Основная группа: взгляд и голова «плывут»", False),
    ("Контрольная", "Участники без нарушений моторики", True),
]
# (код участника, название группы)
PARTICIPANTS = [
    ("P-001", "Нарушения моторики"),
    ("P-002", "Нарушения моторики"),
    ("C-001", "Контрольная"),
    ("C-002", "Контрольная"),
]
# (название, зал, порог dwell-click в мс)
EXHIBITS = [
    ("Картина «Утро»", "Зал 1", 1000),
    ("Скульптура «Равновесие»", "Зал 1", 1000),
    ("Макет старого города", "Зал 2", 1500),
    ("Древняя ваза", "Зал 2", 800),
    ("Интерактивная карта", "Зал 3", 1200),
]


async def seed(db: AsyncSession) -> None:
    for name, description, is_control in GROUPS:
        stmt = pg_insert(ParticipantGroup).values(
            name=name, description=description, is_control=is_control
        )
        await db.execute(stmt.on_conflict_do_nothing(index_elements=["name"]))
    group_ids = dict((await db.execute(select(ParticipantGroup.name, ParticipantGroup.id))).all())

    for code, group_name in PARTICIPANTS:
        stmt = pg_insert(Participant).values(code=code, group_id=group_ids[group_name])
        await db.execute(stmt.on_conflict_do_nothing(index_elements=["code"]))

    for title, hall, dwell_ms in EXHIBITS:
        stmt = pg_insert(Exhibit).values(title=title, hall=hall, dwell_threshold_ms=dwell_ms)
        await db.execute(stmt.on_conflict_do_nothing(index_elements=["title"]))
    await db.commit()


async def _run() -> None:
    try:
        async with SessionLocal() as db:
            await seed(db)
    finally:
        await engine.dispose()
    logger.info(
        "Seed выполнен: групп %d, участников %d, экспонатов %d",
        len(GROUPS),
        len(PARTICIPANTS),
        len(EXHIBITS),
    )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    asyncio.run(_run())


if __name__ == "__main__":
    main()
