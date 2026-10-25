from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Task, User
from app.schemas import TaskCreate, TaskRead, TaskUpdate

router = APIRouter(prefix="/tasks", tags=["tasks"])

NOT_FOUND = {404: {"description": "Задача не найдена"}}


async def get_task_or_404(task_id: int, session: AsyncSession) -> Task:
    task = await session.get(Task, task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Задача не найдена")
    return task


@router.post(
    "",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"description": "Владелец не найден"}},
)
async def create_task(data: TaskCreate, session: AsyncSession = Depends(get_session)):
    if await session.get(User, data.owner_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Владелец задачи не найден")

    task = Task(**data.model_dump())
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


@router.get("", response_model=list[TaskRead])
async def list_tasks(
    done: bool | None = Query(None, description="Фильтр по статусу выполнения"),
    owner_id: int | None = Query(None, description="Фильтр по владельцу"),
    limit: int = Query(20, ge=1, le=100, description="Сколько задач вернуть (1-100)"),
    offset: int = Query(0, ge=0, description="Сколько задач пропустить"),
    session: AsyncSession = Depends(get_session),
):
    query = select(Task)
    if done is not None:
        query = query.where(Task.done == done)
    if owner_id is not None:
        query = query.where(Task.owner_id == owner_id)
    query = query.order_by(Task.id).limit(limit).offset(offset)
    return (await session.scalars(query)).all()


@router.get("/{task_id}", response_model=TaskRead, responses=NOT_FOUND)
async def get_task(task_id: int, session: AsyncSession = Depends(get_session)):
    return await get_task_or_404(task_id, session)


@router.patch("/{task_id}", response_model=TaskRead, responses=NOT_FOUND)
async def update_task(task_id: int, data: TaskUpdate, session: AsyncSession = Depends(get_session)):
    task = await get_task_or_404(task_id, session)
    # exclude_unset: меняем только те поля, которые клиент реально прислал
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(task, field, value)
    await session.commit()
    await session.refresh(task)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT, responses=NOT_FOUND)
async def delete_task(task_id: int, session: AsyncSession = Depends(get_session)):
    task = await get_task_or_404(task_id, session)
    await session.delete(task)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
