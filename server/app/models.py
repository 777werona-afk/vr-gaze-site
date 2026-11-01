"""ORM-модели в стиле SQLAlchemy 2.0 (Mapped + mapped_column)."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # один пользователь — много задач
    tasks: Mapped[list["Task"]] = relationship(back_populates="owner", cascade="all, delete-orphan")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    done: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    owner: Mapped["User"] = relationship(back_populates="tasks")


# ======================================================================================
# Итоговый проект «VR-музей: стабилизация взгляда»
# ======================================================================================

# Жизненный цикл сессии: created -> recorded -> checked -> in_dataset, брак (rejected) — тупик.
SESSION_STATUSES = ("created", "recorded", "checked", "in_dataset", "rejected")


class ParticipantGroup(Base):
    """Группа участников: например, «с нарушениями моторики» или «контрольная»."""

    __tablename__ = "participant_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    is_control: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Participant(Base):
    """Участник записи. Хранится только код, без персональных данных."""

    __tablename__ = "participants"
    __table_args__ = (CheckConstraint("length(code) > 0", name="ck_participants_code_not_empty"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("participant_groups.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Exhibit(Base):
    """Экспонат виртуального музея. Просмотр засчитывается после dwell_threshold_ms."""

    __tablename__ = "exhibits"
    __table_args__ = (
        CheckConstraint("dwell_threshold_ms > 0", name="ck_exhibits_dwell_threshold_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    hall: Mapped[str | None] = mapped_column(String(100))
    dwell_threshold_ms: Mapped[int] = mapped_column(Integer, default=1000, server_default="1000")


class GazeSession(Base):
    """Сессия записи взгляда: метаданные, качество и итог «есть дестабилизация: да/нет»."""

    __tablename__ = "gaze_sessions"
    __table_args__ = (
        UniqueConstraint("source_sha256", name="uq_gaze_sessions_source_sha256"),
        CheckConstraint(
            "status IN ('created', 'recorded', 'checked', 'in_dataset', 'rejected')",
            name="ck_gaze_sessions_status",
        ),
        CheckConstraint(
            "valid_pct IS NULL OR (valid_pct >= 0 AND valid_pct <= 100)",
            name="ck_gaze_sessions_valid_pct_range",
        ),
        CheckConstraint(
            "valid_rows >= 0 AND valid_rows <= total_rows", name="ck_gaze_sessions_rows"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("participants.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default="created", server_default="created", index=True
    )
    source_file: Mapped[str | None] = mapped_column(String(255))
    # SHA-256 содержимого CSV: по нему ETL понимает, что файл уже загружен (идемпотентность)
    source_sha256: Mapped[str | None] = mapped_column(String(64))
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    total_rows: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    valid_rows: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    valid_pct: Mapped[float | None] = mapped_column(Float)
    fs_hz: Mapped[float | None] = mapped_column(Float)
    duration_s: Mapped[float | None] = mapped_column(Float)
    tremor_rms_deg: Mapped[float | None] = mapped_column(Float)
    # итог проекта: есть ли дестабилизация взгляда (True = да, False = нет, None = не оценено)
    destabilized: Mapped[bool | None] = mapped_column(Boolean)
    reject_reason: Mapped[str | None] = mapped_column(String(255))


class GazeSample(Base):
    """Один отсчёт лога взгляда (строка CSV после очистки)."""

    __tablename__ = "gaze_samples"
    __table_args__ = (UniqueConstraint("session_id", "t_s", name="uq_gaze_samples_session_t"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("gaze_sessions.id", ondelete="CASCADE"))
    t_s: Mapped[float] = mapped_column(Float)
    x: Mapped[float] = mapped_column(Float)
    y: Mapped[float] = mapped_column(Float)
    z: Mapped[float] = mapped_column(Float)
    pupil: Mapped[float | None] = mapped_column(Float)
    openness: Mapped[float | None] = mapped_column(Float)


class ExhibitView(Base):
    """Ассоциативная таблица «сессия — экспонат» (N:M): сколько взгляд удерживался на экспонате."""

    __tablename__ = "exhibit_views"
    __table_args__ = (
        CheckConstraint("dwell_ms > 0", name="ck_exhibit_views_dwell_positive"),
        CheckConstraint("views_count >= 1", name="ck_exhibit_views_count_positive"),
    )

    session_id: Mapped[int] = mapped_column(
        ForeignKey("gaze_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    exhibit_id: Mapped[int] = mapped_column(
        ForeignKey("exhibits.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    dwell_ms: Mapped[int] = mapped_column(Integer)
    views_count: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
