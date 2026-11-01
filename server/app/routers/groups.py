from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import ParticipantGroup
from app.schemas import GroupCreate, GroupRead
from app.services.db_utils import commit_or_conflict
from app.services.errors import ConflictError

router = APIRouter(prefix="/groups", tags=["groups"])

NAME_TAKEN = "Группа с таким названием уже существует"


@router.post(
    "",
    response_model=GroupRead,
    status_code=status.HTTP_201_CREATED,
    summary="Создать группу участников",
    responses={409: {"description": "Название группы уже занято"}},
)
async def create_group(data: GroupCreate, db: AsyncSession = Depends(get_session)):
    if await db.scalar(select(ParticipantGroup.id).where(ParticipantGroup.name == data.name)):
        raise ConflictError(NAME_TAKEN)
    group = ParticipantGroup(**data.model_dump())
    db.add(group)
    await commit_or_conflict(db, NAME_TAKEN)
    await db.refresh(group)
    return group


@router.get("", response_model=list[GroupRead], summary="Список групп участников")
async def list_groups(db: AsyncSession = Depends(get_session)):
    return (await db.scalars(select(ParticipantGroup).order_by(ParticipantGroup.id))).all()
