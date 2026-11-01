"""vr gaze domain: groups, participants, exhibits, sessions, samples, exhibit views

Revision ID: c3f81d2a9b64
Revises: b5115085ef73
Create Date: 2026-11-02 00:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3f81d2a9b64"
down_revision: str | Sequence[str] | None = "b5115085ef73"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создаёт шесть таблиц предметной области «VR-музей: стабилизация взгляда»."""
    op.create_table(
        "participant_groups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_control", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_participant_groups_name"), "participant_groups", ["name"], unique=True
    )

    op.create_table(
        "participants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint("length(code) > 0", name="ck_participants_code_not_empty"),
        sa.ForeignKeyConstraint(["group_id"], ["participant_groups.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_participants_code"), "participants", ["code"], unique=True)
    op.create_index(op.f("ix_participants_group_id"), "participants", ["group_id"], unique=False)

    op.create_table(
        "exhibits",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("hall", sa.String(length=100), nullable=True),
        sa.Column("dwell_threshold_ms", sa.Integer(), server_default="1000", nullable=False),
        sa.CheckConstraint("dwell_threshold_ms > 0", name="ck_exhibits_dwell_threshold_positive"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_exhibits_title"), "exhibits", ["title"], unique=True)

    op.create_table(
        "gaze_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("participant_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="created", nullable=False),
        sa.Column("source_file", sa.String(length=255), nullable=True),
        sa.Column("source_sha256", sa.String(length=64), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("total_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("valid_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("valid_pct", sa.Float(), nullable=True),
        sa.Column("fs_hz", sa.Float(), nullable=True),
        sa.Column("duration_s", sa.Float(), nullable=True),
        sa.Column("tremor_rms_deg", sa.Float(), nullable=True),
        sa.Column("destabilized", sa.Boolean(), nullable=True),
        sa.Column("reject_reason", sa.String(length=255), nullable=True),
        sa.CheckConstraint(
            "status IN ('created', 'recorded', 'checked', 'in_dataset', 'rejected')",
            name="ck_gaze_sessions_status",
        ),
        sa.CheckConstraint(
            "valid_pct IS NULL OR (valid_pct >= 0 AND valid_pct <= 100)",
            name="ck_gaze_sessions_valid_pct_range",
        ),
        sa.CheckConstraint("valid_rows >= 0 AND valid_rows <= total_rows", name="ck_gaze_sessions_rows"),
        sa.ForeignKeyConstraint(["participant_id"], ["participants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_sha256", name="uq_gaze_sessions_source_sha256"),
    )
    op.create_index(
        op.f("ix_gaze_sessions_participant_id"), "gaze_sessions", ["participant_id"], unique=False
    )
    op.create_index(op.f("ix_gaze_sessions_status"), "gaze_sessions", ["status"], unique=False)

    op.create_table(
        "gaze_samples",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("t_s", sa.Float(), nullable=False),
        sa.Column("x", sa.Float(), nullable=False),
        sa.Column("y", sa.Float(), nullable=False),
        sa.Column("z", sa.Float(), nullable=False),
        sa.Column("pupil", sa.Float(), nullable=True),
        sa.Column("openness", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["gaze_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "t_s", name="uq_gaze_samples_session_t"),
    )

    op.create_table(
        "exhibit_views",
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("exhibit_id", sa.Integer(), nullable=False),
        sa.Column("dwell_ms", sa.Integer(), nullable=False),
        sa.Column("views_count", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint("dwell_ms > 0", name="ck_exhibit_views_dwell_positive"),
        sa.CheckConstraint("views_count >= 1", name="ck_exhibit_views_count_positive"),
        sa.ForeignKeyConstraint(["exhibit_id"], ["exhibits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["gaze_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("session_id", "exhibit_id"),
    )
    op.create_index(
        op.f("ix_exhibit_views_exhibit_id"), "exhibit_views", ["exhibit_id"], unique=False
    )


def downgrade() -> None:
    """Откатывает миграцию: таблицы удаляются в порядке, обратном зависимостям."""
    op.drop_index(op.f("ix_exhibit_views_exhibit_id"), table_name="exhibit_views")
    op.drop_table("exhibit_views")
    op.drop_table("gaze_samples")
    op.drop_index(op.f("ix_gaze_sessions_status"), table_name="gaze_sessions")
    op.drop_index(op.f("ix_gaze_sessions_participant_id"), table_name="gaze_sessions")
    op.drop_table("gaze_sessions")
    op.drop_index(op.f("ix_exhibits_title"), table_name="exhibits")
    op.drop_table("exhibits")
    op.drop_index(op.f("ix_participants_group_id"), table_name="participants")
    op.drop_index(op.f("ix_participants_code"), table_name="participants")
    op.drop_table("participants")
    op.drop_index(op.f("ix_participant_groups_name"), table_name="participant_groups")
    op.drop_table("participant_groups")
