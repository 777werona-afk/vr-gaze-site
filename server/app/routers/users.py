from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import User
from app.schemas import UserCreate, UserRead

router = APIRouter(prefix="/users", tags=["users"])


@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "Email уже занят"}},
)
async def create_user(data: UserCreate, session: AsyncSession = Depends(get_session)):
    exists = await session.scalar(select(User.id).where(User.email == data.email))
    if exists is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Пользователь с таким email уже существует")

    user = User(**data.model_dump())
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:  # гонка: email заняли между проверкой и вставкой
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Пользователь с таким email уже существует")
    await session.refresh(user)
    return user


@router.get(
    "/{user_id}",
    response_model=UserRead,
    responses={404: {"description": "Пользователь не найден"}},
)
async def get_user(user_id: int, session: AsyncSession = Depends(get_session)):
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден")
    return user
