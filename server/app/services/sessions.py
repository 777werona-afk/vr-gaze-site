"""Бизнес-операции над сессиями (слой services).

Три правила сверх CRUD:
1. Контроль качества: проверка сессии даёт статус «checked» или «брак» (rejected) и ответ
   «есть дестабилизация — да/нет» (см. quality.evaluate_session).
2. Жизненный цикл: created -> recorded -> checked -> in_dataset, обратно и мимо шагов нельзя.
3. Dwell-click: просмотр экспоната засчитывается, только если взгляд удерживался не меньше
   порога экспоната; повторные просмотры суммируются в одной записи.
"""

import numpy as np
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Exhibit, ExhibitView, GazeSample, GazeSession
from app.services.errors import ConflictError, NotFoundError, RuleViolationError
from app.services.quality import can_transition, evaluate_session

VIEWABLE_STATUSES = ("recorded", "checked", "in_dataset")


async def get_session_or_404(db: AsyncSession, session_id: int) -> GazeSession:
    session = await db.get(GazeSession, session_id)
    if session is None:
        raise NotFoundError("Сессия не найдена")
    return session


def _require_transition(session: GazeSession, target: str, hint: str) -> None:
    if not can_transition(session.status, target):
        raise ConflictError(f"Сессия в статусе '{session.status}': {hint}")


async def check_session(db: AsyncSession, session_id: int) -> GazeSession:
    """Проверяет записанную сессию: контроль качества и итог «дестабилизация: да/нет»."""
    session = await get_session_or_404(db, session_id)
    _require_transition(session, "checked", "проверить можно только записанную сессию (recorded)")

    rows = (
        await db.execute(
            select(GazeSample.t_s, GazeSample.x, GazeSample.y, GazeSample.z)
            .where(GazeSample.session_id == session_id)
            .order_by(GazeSample.t_s)
        )
    ).all()
    t = np.array([row[0] for row in rows], dtype=float)
    xyz = np.array([[row[1], row[2], row[3]] for row in rows], dtype=float).reshape(-1, 3)

    verdict = evaluate_session(
        session.valid_pct,
        t,
        xyz,
        threshold_deg=settings.tremor_threshold_deg,
        min_valid_pct=settings.min_valid_pct,
    )
    session.status = verdict.status
    session.reject_reason = verdict.reason
    session.destabilized = verdict.destabilized
    if verdict.assessment is not None:
        session.tremor_rms_deg = verdict.assessment.tremor_rms_deg
        session.fs_hz = verdict.assessment.fs_hz
        session.duration_s = verdict.assessment.duration_s
    await db.commit()
    await db.refresh(session)
    return session


async def publish_session(db: AsyncSession, session_id: int) -> GazeSession:
    """Переводит проверенную сессию в датасет. Брак и непроверенные сессии не публикуются."""
    session = await get_session_or_404(db, session_id)
    if session.status == "rejected":
        raise ConflictError("Сессия забракована и в датасет не попадает")
    _require_transition(
        session, "in_dataset", "в датасет можно добавить только проверенную сессию (checked)"
    )
    session.status = "in_dataset"
    await db.commit()
    await db.refresh(session)
    return session


async def register_view(
    db: AsyncSession, session_id: int, exhibit_id: int, dwell_ms: int
) -> ExhibitView:
    """Засчитывает просмотр экспоната, если взгляд удерживался не короче порога dwell-click."""
    session = await get_session_or_404(db, session_id)
    if session.status not in VIEWABLE_STATUSES:
        raise ConflictError(
            f"Сессия в статусе '{session.status}': просмотры регистрируются только для "
            "записанных, проверенных и опубликованных сессий"
        )
    exhibit = await db.get(Exhibit, exhibit_id)
    if exhibit is None:
        raise NotFoundError("Экспонат не найден")
    if dwell_ms < exhibit.dwell_threshold_ms:
        raise RuleViolationError(
            f"Взгляд удерживался {dwell_ms} мс, порог dwell-click для экспоната "
            f"{exhibit.dwell_threshold_ms} мс: просмотр не засчитан"
        )

    # один атомарный upsert: повторный просмотр суммирует время и увеличивает счётчик
    stmt = pg_insert(ExhibitView).values(
        session_id=session_id, exhibit_id=exhibit_id, dwell_ms=dwell_ms, views_count=1
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[ExhibitView.session_id, ExhibitView.exhibit_id],
        set_={
            "dwell_ms": ExhibitView.dwell_ms + stmt.excluded.dwell_ms,
            "views_count": ExhibitView.views_count + 1,
        },
    )
    await db.execute(stmt)
    await db.commit()
    view = await db.get(ExhibitView, (session_id, exhibit_id), populate_existing=True)
    if view is None:  # недостижимо: upsert выше только что создал или обновил запись
        raise ConflictError("Не удалось сохранить просмотр")
    return view
