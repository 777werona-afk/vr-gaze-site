"""Аналитика поверх БД: агрегации по экспонатам и по группам участников.

В расчёты попадают только проверенные сессии (checked, in_dataset): брак «в аналитику не идёт».
"""

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Exhibit,
    ExhibitView,
    GazeSession,
    Participant,
    ParticipantGroup,
)

ANALYTICS_STATUSES = ("checked", "in_dataset")


async def dwell_by_exhibit(db: AsyncSession, top: int) -> list[dict]:
    """Топ-N экспонатов по суммарному времени удержания взгляда."""
    total = func.sum(ExhibitView.dwell_ms)
    stmt = (
        select(
            Exhibit.id.label("exhibit_id"),
            Exhibit.title,
            func.count(ExhibitView.session_id).label("sessions_count"),
            func.sum(ExhibitView.views_count).label("views_total"),
            total.label("total_dwell_ms"),
            func.avg(ExhibitView.dwell_ms).label("avg_dwell_ms"),
        )
        .join(ExhibitView, ExhibitView.exhibit_id == Exhibit.id)
        .join(GazeSession, GazeSession.id == ExhibitView.session_id)
        .where(GazeSession.status.in_(ANALYTICS_STATUSES))
        .group_by(Exhibit.id, Exhibit.title)
        .order_by(total.desc(), Exhibit.id)
        .limit(top)
    )
    return [
        {
            "exhibit_id": row.exhibit_id,
            "title": row.title,
            "sessions_count": int(row.sessions_count),
            "views_total": int(row.views_total),
            "total_dwell_ms": int(row.total_dwell_ms),
            "avg_dwell_ms": float(row.avg_dwell_ms),
        }
        for row in (await db.execute(stmt)).all()
    ]


async def stability_by_group(db: AsyncSession) -> list[dict]:
    """По каждой группе: сколько сессий с дестабилизацией «да» и «нет», сколько в браке."""
    analyzed = GazeSession.status.in_(ANALYTICS_STATUSES)
    stmt = (
        select(
            ParticipantGroup.id.label("group_id"),
            ParticipantGroup.name.label("group_name"),
            ParticipantGroup.is_control,
            func.sum(case((analyzed, 1), else_=0)).label("sessions_analyzed"),
            func.sum(case((and_(analyzed, GazeSession.destabilized.is_(True)), 1), else_=0)).label(
                "destabilized_yes"
            ),
            func.sum(case((and_(analyzed, GazeSession.destabilized.is_(False)), 1), else_=0)).label(
                "destabilized_no"
            ),
            func.sum(case((GazeSession.status == "rejected", 1), else_=0)).label("rejected"),
            func.avg(case((analyzed, GazeSession.tremor_rms_deg))).label("mean_tremor_rms_deg"),
        )
        .select_from(ParticipantGroup)
        .outerjoin(Participant, Participant.group_id == ParticipantGroup.id)
        .outerjoin(GazeSession, GazeSession.participant_id == Participant.id)
        .group_by(ParticipantGroup.id, ParticipantGroup.name, ParticipantGroup.is_control)
        .order_by(ParticipantGroup.id)
    )
    result = []
    for row in (await db.execute(stmt)).all():
        n = int(row.sessions_analyzed)
        yes = int(row.destabilized_yes)
        result.append(
            {
                "group_id": row.group_id,
                "group_name": row.group_name,
                "is_control": row.is_control,
                "sessions_analyzed": n,
                "destabilized_yes": yes,
                "destabilized_no": int(row.destabilized_no),
                "rejected": int(row.rejected),
                "share_yes": yes / n if n else None,
                "mean_tremor_rms_deg": (
                    float(row.mean_tremor_rms_deg) if row.mean_tremor_rms_deg is not None else None
                ),
            }
        )
    return result
