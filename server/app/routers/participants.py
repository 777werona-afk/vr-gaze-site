from typing import Literal

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import GazeSession, Participant, ParticipantGroup
from app.schemas import ParticipantCreate, ParticipantRead, ParticipantUpdate
from app.services.db_utils import commit_or_conflict
from app.services.errors import ConflictError, NotFoundError

router = APIRouter(prefix="/participants", tags=["participants"])

CODE_TAKEN = "Участник с таким кодом уже существует"
SORT_COLUMNS = {"id": Participant.id, "code": Participant.code}


async def _ensure_group(db: AsyncSession, group_id: int) -> None:
    if await db.get(ParticipantGroup, group_id) is None:
        raise NotFoundError("Группа не найдена")


async def _get_or_404(db: AsyncSession, participant_id: int) -> Participant:
    participant = await db.get(Participant, participant_id)
    if participant is None:
        raise NotFoundError("Участник не найден")
    return participant


@router.post(
    "",
    response_model=ParticipantRead,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить участника",
    responses={404: {"description": "Группа не найдена"}, 409: {"description": "Код занят"}},
)
async def create_participant(data: ParticipantCreate, db: AsyncSession = Depends(get_session)):
    await _ensure_group(db, data.group_id)
    if await db.scalar(select(Participant.id).where(Participant.code == data.code)):
        raise ConflictError(CODE_TAKEN)
    participant = Participant(**data.model_dump())
    db.add(participant)
    await commit_or_conflict(db, CODE_TAKEN)
    await db.refresh(participant)
    return participant


@router.get("", response_model=list[ParticipantRead], summary="Список участников")
async def list_participants(
    group_id: int | None = Query(None, description="Фильтр по группе"),
    sort: Literal["id", "-id", "code", "-code"] = Query("id", description="Сортировка"),
    limit: int = Query(20, ge=1, le=100, description="Сколько участников вернуть (1-100)"),
    offset: int = Query(0, ge=0, description="Сколько участников пропустить"),
    db: AsyncSession = Depends(get_session),
):
    query = select(Participant)
    if group_id is not None:
        query = query.where(Participant.group_id == group_id)
    column = SORT_COLUMNS[sort.lstrip("-")]
    query = query.order_by(column.desc() if sort.startswith("-") else column.asc())
    return (await db.scalars(query.limit(limit).offset(offset))).all()


@router.get(
    "/{participant_id}",
    response_model=ParticipantRead,
    summary="Участник по id",
    responses={404: {"description": "Участник не найден"}},
)
async def get_participant(participant_id: int, db: AsyncSession = Depends(get_session)):
    return await _get_or_404(db, participant_id)


@router.patch(
    "/{participant_id}",
    response_model=ParticipantRead,
    summary="Изменить участника",
    responses={
        404: {"description": "Участник или группа не найдены"},
        409: {"description": "Код занят"},
    },
)
async def update_participant(
    participant_id: int, data: ParticipantUpdate, db: AsyncSession = Depends(get_session)
):
    participant = await _get_or_404(db, participant_id)
    changes = data.model_dump(exclude_unset=True)
    if "group_id" in changes:
        await _ensure_group(db, changes["group_id"])
    if "code" in changes and changes["code"] != participant.code:
        if await db.scalar(select(Participant.id).where(Participant.code == changes["code"])):
            raise ConflictError(CODE_TAKEN)
    for field, value in changes.items():
        setattr(participant, field, value)
    await commit_or_conflict(db, CODE_TAKEN)
    await db.refresh(participant)
    return participant


@router.delete(
    "/{participant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить участника",
    responses={404: {"description": "Участник не найден"}, 409: {"description": "Есть сессии"}},
)
async def delete_participant(participant_id: int, db: AsyncSession = Depends(get_session)):
    participant = await _get_or_404(db, participant_id)
    owned = select(func.count()).select_from(GazeSession)
    sessions = await db.scalar(owned.where(GazeSession.participant_id == participant_id))
    if sessions:
        raise ConflictError(f"У участника есть сессии ({sessions}): сначала удалите их")
    await db.delete(participant)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
