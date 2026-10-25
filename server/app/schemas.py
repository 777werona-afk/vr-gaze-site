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
