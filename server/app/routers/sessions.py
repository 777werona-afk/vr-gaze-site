from typing import Literal

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.models import ExhibitView, GazeSession, Participant
from app.schemas import SessionCreate, SessionRead, StabilityRead, ViewCreate, ViewRead
from app.services import sessions as session_service
from app.services.errors import ConflictError, NotFoundError

router = APIRouter(prefix="/sessions", tags=["sessions"])

SessionStatus = Literal["created", "recorded", "checked", "in_dataset", "rejected"]
SORT_COLUMNS = {
    "id": GazeSession.id,
    "recorded_at": GazeSession.recorded_at,
    "tremor_rms_deg": GazeSession.tremor_rms_deg,
}
NOT_FOUND = {404: {"description": "Сессия не найдена"}}


@router.post(
    "",
    response_model=SessionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Создать сессию (статус created)",
    responses={404: {"description": "Участник не найден"}},
)
async def create_session(data: SessionCreate, db: AsyncSession = Depends(get_session)):
    if await db.get(Participant, data.participant_id) is None:
        raise NotFoundError("Участник не найден")
    session = GazeSession(**data.model_dump())
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.get("", response_model=list[SessionRead], summary="Список сессий")
async def list_sessions(
    status_: SessionStatus | None = Query(None, alias="status", description="Фильтр по статусу"),
    participant_id: int | None = Query(None, description="Фильтр по участнику"),
    group_id: int | None = Query(None, description="Фильтр по группе участника"),
    destabilized: bool | None = Query(None, description="Фильтр по ответу «да/нет»"),
    sort: Literal[
        "id", "-id", "recorded_at", "-recorded_at", "tremor_rms_deg", "-tremor_rms_deg"
    ] = Query("id", description="Сортировка; минус перед полем — по убыванию"),
    limit: int = Query(20, ge=1, le=100, description="Сколько сессий вернуть (1-100)"),
    offset: int = Query(0, ge=0, description="Сколько сессий пропустить"),
    db: AsyncSession = Depends(get_session),
):
    query = select(GazeSession)
    if status_ is not None:
        query = query.where(GazeSession.status == status_)
    if participant_id is not None:
        query = query.where(GazeSession.participant_id == participant_id)
    if group_id is not None:
        query = query.join(Participant, Participant.id == GazeSession.participant_id).where(
            Participant.group_id == group_id
        )
    if destabilized is not None:
        query = query.where(GazeSession.destabilized.is_(destabilized))
    column = SORT_COLUMNS[sort.lstrip("-")]
    ordering = column.desc() if sort.startswith("-") else column.asc()
    query = query.order_by(ordering.nulls_last(), GazeSession.id)
    return (await db.scalars(query.limit(limit).offset(offset))).all()


@router.get(
    "/{session_id}", response_model=SessionRead, summary="Сессия по id", responses=NOT_FOUND
)
async def get_session_by_id(session_id: int, db: AsyncSession = Depends(get_session)):
    return await session_service.get_session_or_404(db, session_id)


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить сессию вместе с отсчётами и просмотрами",
    responses=NOT_FOUND,
)
async def delete_session(session_id: int, db: AsyncSession = Depends(get_session)):
    session = await session_service.get_session_or_404(db, session_id)
    await db.delete(session)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{session_id}/check",
    response_model=SessionRead,
    summary="Проверить сессию: контроль качества и «дестабилизация: да/нет»",
    responses={**NOT_FOUND, 409: {"description": "Сессия не в статусе recorded"}},
)
async def check_session(session_id: int, db: AsyncSession = Depends(get_session)):
    return await session_service.check_session(db, session_id)


@router.post(
    "/{session_id}/publish",
    response_model=SessionRead,
    summary="Добавить проверенную сессию в датасет",
    responses={**NOT_FOUND, 409: {"description": "Сессия не проверена или забракована"}},
)
async def publish_session(session_id: int, db: AsyncSession = Depends(get_session)):
    return await session_service.publish_session(db, session_id)


@router.get(
    "/{session_id}/stability",
    response_model=StabilityRead,
    summary="Ответ по сессии: есть дестабилизация взгляда или нет",
    responses={**NOT_FOUND, 409: {"description": "Сессия ещё не проверена"}},
)
async def get_stability(session_id: int, db: AsyncSession = Depends(get_session)):
    session = await session_service.get_session_or_404(db, session_id)
    if session.status in ("created", "recorded"):
        raise ConflictError("Сессия ещё не проверена: вызовите POST /sessions/{id}/check")
    if session.status == "rejected":
        verdict = f"брак: {session.reject_reason}"
    else:
        verdict = "да" if session.destabilized else "нет"
    return StabilityRead(
        session_id=session.id,
        status=session.status,
        destabilized=session.destabilized,
        tremor_rms_deg=session.tremor_rms_deg,
        threshold_deg=settings.tremor_threshold_deg,
        verdict=verdict,
    )


@router.post(
    "/{session_id}/views",
    response_model=ViewRead,
    status_code=status.HTTP_201_CREATED,
    summary="Засчитать просмотр экспоната (dwell-click)",
    responses={
        **NOT_FOUND,
        409: {"description": "Сессия в неподходящем статусе"},
        422: {"description": "Взгляд удерживался короче порога экспоната"},
    },
)
async def add_view(session_id: int, data: ViewCreate, db: AsyncSession = Depends(get_session)):
    return await session_service.register_view(db, session_id, data.exhibit_id, data.dwell_ms)


@router.get(
    "/{session_id}/views",
    response_model=list[ViewRead],
    summary="Просмотры экспонатов в сессии",
    responses=NOT_FOUND,
)
async def list_views(session_id: int, db: AsyncSession = Depends(get_session)):
    await session_service.get_session_or_404(db, session_id)
    query = select(ExhibitView).where(ExhibitView.session_id == session_id)
    return (await db.scalars(query.order_by(ExhibitView.exhibit_id))).all()
