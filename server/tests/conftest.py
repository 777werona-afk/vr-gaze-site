"""Фикстуры для тестов API на реальной PostgreSQL.

- отдельная тестовая БД tasks_test (создаётся автоматически, если её нет);
- схема создаётся миграциями Alembic (как в production), после тестов откатывается;
- каждый тест работает на чистых таблицах (TRUNCATE ... RESTART IDENTITY);
- зависимость get_session подменяется через app.dependency_overrides.
"""

import os
import subprocess
import sys
from pathlib import Path

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5432/tasks_test"
)
# Приложение читает DATABASE_URL при импорте (pydantic-settings), поэтому задаём его заранее.
os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL)

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.db import get_session  # noqa: E402
from app.main import app  # noqa: E402

SERVER_DIR = Path(__file__).resolve().parents[1]


async def _ensure_test_database() -> None:
    """Создаёт БД tasks_test, если её ещё нет (подключаемся к служебной БД postgres)."""
    url = make_url(TEST_DATABASE_URL)
    admin = create_async_engine(
        url.set(database="postgres"), isolation_level="AUTOCOMMIT", poolclass=NullPool
    )
    async with admin.connect() as conn:
        exists = await conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}
        )
        if not exists:
            await conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    await admin.dispose()


def _alembic(*args: str) -> None:
    """Запускает alembic отдельным процессом с DATABASE_URL тестовой БД."""
    env = {**os.environ, "DATABASE_URL": TEST_DATABASE_URL}
    subprocess.run([sys.executable, "-m", "alembic", *args], cwd=SERVER_DIR, env=env, check=True)


@pytest_asyncio.fixture(scope="session")
async def engine():
    await _ensure_test_database()
    _alembic("downgrade", "base")  # на случай, если прошлый прогон оборвался
    _alembic("upgrade", "head")
    test_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    yield test_engine
    await test_engine.dispose()
    _alembic("downgrade", "base")


@pytest_asyncio.fixture(autouse=True)
async def clean_tables(engine):
    """Каждый тест начинается с пустых таблиц и счётчиков id с единицы."""
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE tasks, users RESTART IDENTITY CASCADE"))
    yield


@pytest_asyncio.fixture
async def client(engine):
    """HTTP-клиент к приложению; сессии БД берутся из тестового движка."""
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def user(client):
    """Готовый пользователь для тестов задач."""
    resp = await client.post("/users", json={"email": "owner@example.com", "name": "Владелец"})
    assert resp.status_code == 201
    return resp.json()
