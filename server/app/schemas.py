"""Pydantic-схемы: отдельные *Create, *Read и *Update для каждой сущности."""

from datetime import datetime
from typing import Annotated, ClassVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

Name = Annotated[str, Field(min_length=1, max_length=100)]
Title = Annotated[str, Field(min_length=1, max_length=200)]


class _NoNullUpdates(BaseModel):
    """В PATCH поля необязательны, но явный null для обязательных колонок запрещён."""

    not_nullable: ClassVar[tuple[str, ...]] = ()

    @model_validator(mode="after")
    def _forbid_explicit_null(self):
        for field in self.not_nullable:
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"Поле '{field}' не может быть null")
        return self


# ---------- User ----------


class UserCreate(BaseModel):
    email: EmailStr
    name: Name


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    name: str
    created_at: datetime


class UserUpdate(_NoNullUpdates):
    not_nullable: ClassVar[tuple[str, ...]] = ("email", "name")

    email: EmailStr | None = None
    name: Name | None = None


# ---------- Task ----------


class TaskCreate(BaseModel):
    title: Title
    description: str | None = None
    done: bool = False
    owner_id: int


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    done: bool
    created_at: datetime
    owner_id: int


class TaskUpdate(_NoNullUpdates):
    not_nullable: ClassVar[tuple[str, ...]] = ("title", "done")

    title: Title | None = None
    description: str | None = None
    done: bool | None = None


# ======================================================================================
# Итоговый проект «VR-музей: стабилизация взгляда»
# ======================================================================================

Code = Annotated[str, Field(min_length=1, max_length=50)]
GroupName = Annotated[str, Field(min_length=1, max_length=100)]
ExhibitTitle = Annotated[str, Field(min_length=1, max_length=200)]


# ---------- Group ----------


class GroupCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "Нарушения моторики",
                    "description": "Основная группа",
                    "is_control": False,
                }
            ]
        }
    )

    name: GroupName
    description: str | None = None
    is_control: bool = False


class GroupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    is_control: bool
    created_at: datetime


# ---------- Participant ----------


class ParticipantCreate(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"code": "P-001", "group_id": 1}]})

    code: Code
    group_id: int


class ParticipantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    group_id: int
    created_at: datetime


class ParticipantUpdate(_NoNullUpdates):
    not_nullable: ClassVar[tuple[str, ...]] = ("code", "group_id")

    code: Code | None = None
    group_id: int | None = None


# ---------- Exhibit ----------


class ExhibitCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"title": "Картина «Утро»", "hall": "Зал 1", "dwell_threshold_ms": 1000}]
        }
    )

    title: ExhibitTitle
    hall: str | None = Field(None, max_length=100)
    dwell_threshold_ms: int = Field(
        1000, gt=0, le=60000, description="Сколько мс взгляд должен удерживаться на экспонате"
    )


class ExhibitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    hall: str | None
    dwell_threshold_ms: int


# ---------- Session ----------


class SessionCreate(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"participant_id": 1}]})

    participant_id: int
    recorded_at: datetime | None = None


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    participant_id: int
    status: str = Field(description="created, recorded, checked, in_dataset или rejected (брак)")
    source_file: str | None
    recorded_at: datetime | None
    created_at: datetime
    total_rows: int
    valid_rows: int
    valid_pct: float | None
    fs_hz: float | None
    duration_s: float | None
    tremor_rms_deg: float | None = Field(description="RMS колебаний взгляда в полосе 4-12 Гц, °")
    destabilized: bool | None = Field(
        description="Есть ли дестабилизация взгляда: true — да, false — нет, null — не оценено"
    )
    reject_reason: str | None


class StabilityRead(BaseModel):
    """Итог проекта по одной сессии: есть дестабилизация взгляда или нет."""

    session_id: int
    status: str
    destabilized: bool | None
    tremor_rms_deg: float | None
    threshold_deg: float
    verdict: str = Field(description="Текстовый ответ: «да», «нет» или причина брака")


# ---------- Views ----------


class ViewCreate(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"exhibit_id": 1, "dwell_ms": 1500}]})

    exhibit_id: int
    dwell_ms: int = Field(gt=0, le=3_600_000, description="Сколько мс взгляд удерживался")


class ViewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: int
    exhibit_id: int
    dwell_ms: int
    views_count: int


# ---------- Analytics ----------


class DwellByExhibitRead(BaseModel):
    exhibit_id: int
    title: str
    sessions_count: int
    views_total: int
    total_dwell_ms: int
    avg_dwell_ms: float


class StabilityByGroupRead(BaseModel):
    group_id: int
    group_name: str
    is_control: bool
    sessions_analyzed: int
    destabilized_yes: int
    destabilized_no: int
    rejected: int
    share_yes: float | None = Field(description="Доля сессий с дестабилизацией «да»")
    mean_tremor_rms_deg: float | None
