from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas import DwellByExhibitRead, StabilityByGroupRead
from app.services import analytics as analytics_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get(
    "/dwell-by-exhibit",
    response_model=list[DwellByExhibitRead],
    summary="Топ-N экспонатов по времени удержания взгляда",
)
async def dwell_by_exhibit(
    top: int = Query(5, ge=1, le=50, description="Сколько экспонатов вернуть (1-50)"),
    db: AsyncSession = Depends(get_session),
):
    """Только проверенные сессии (checked, in_dataset): брак в аналитику не попадает."""
    return await analytics_service.dwell_by_exhibit(db, top)


@router.get(
    "/stability-by-group",
    response_model=list[StabilityByGroupRead],
    summary="Дестабилизация «да/нет» по группам участников",
)
async def stability_by_group(db: AsyncSession = Depends(get_session)):
    """Сколько сессий с дестабилизацией «да» и «нет» в каждой группе, и сколько в браке."""
    return await analytics_service.stability_by_group(db)
