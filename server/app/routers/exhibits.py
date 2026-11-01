from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Exhibit
from app.schemas import ExhibitCreate, ExhibitRead
from app.services.db_utils import commit_or_conflict
from app.services.errors import ConflictError, NotFoundError

router = APIRouter(prefix="/exhibits", tags=["exhibits"])

TITLE_TAKEN = "Экспонат с таким названием уже существует"


@router.post(
    "",
    response_model=ExhibitRead,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить экспонат",
    responses={409: {"description": "Название экспоната уже занято"}},
)
async def create_exhibit(data: ExhibitCreate, db: AsyncSession = Depends(get_session)):
    if await db.scalar(select(Exhibit.id).where(Exhibit.title == data.title)):
        raise ConflictError(TITLE_TAKEN)
    exhibit = Exhibit(**data.model_dump())
    db.add(exhibit)
    await commit_or_conflict(db, TITLE_TAKEN)
    await db.refresh(exhibit)
    return exhibit


@router.get("", response_model=list[ExhibitRead], summary="Список экспонатов")
async def list_exhibits(
    limit: int = Query(50, ge=1, le=200, description="Сколько экспонатов вернуть (1-200)"),
    offset: int = Query(0, ge=0, description="Сколько экспонатов пропустить"),
    db: AsyncSession = Depends(get_session),
):
    query = select(Exhibit).order_by(Exhibit.id).limit(limit).offset(offset)
    return (await db.scalars(query)).all()


@router.get(
    "/{exhibit_id}",
    response_model=ExhibitRead,
    summary="Экспонат по id",
    responses={404: {"description": "Экспонат не найден"}},
)
async def get_exhibit(exhibit_id: int, db: AsyncSession = Depends(get_session)):
    exhibit = await db.get(Exhibit, exhibit_id)
    if exhibit is None:
        raise NotFoundError("Экспонат не найден")
    return exhibit
