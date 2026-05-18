"""Integration test fixtures: real Postgres + Redis via testcontainers.

Tests under tests/integration/ should be decorated with
@pytest.mark.integration. They are skipped by default in the standard
pytest run; CI runs them in a separate job, locally trigger via
`make test-integration`.

Container startup cost is amortised by session scope.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator  # noqa: TC003  runtime fixture types
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    container = PostgresContainer(
        "postgres:15-alpine",
        username="ai_team",
        password="test-pass",
        dbname="ai_team",
    )
    container.start()
    yield container
    container.stop()


@pytest.fixture(scope="session")
def redis_container() -> Iterator[RedisContainer]:
    container = RedisContainer("redis:7-alpine")
    container.start()
    yield container
    container.stop()


@pytest.fixture(scope="session")
def pg_dsn(postgres_container: PostgresContainer) -> str:
    raw: str = str(postgres_container.get_connection_url())
    # testcontainers returns a sync DSN; convert to asyncpg.
    return raw.replace("postgresql+psycopg2://", "postgresql+asyncpg://").replace(
        "postgresql://", "postgresql+asyncpg://", 1
    )


@pytest.fixture(scope="session")
def redis_url(redis_container: RedisContainer) -> str:
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    return f"redis://{host}:{port}/0"


@pytest.fixture(scope="session", autouse=True)
def _alembic_upgrade(pg_dsn: str) -> None:
    env = os.environ.copy()
    env["POSTGRES_DSN"] = pg_dsn
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT, env=env, check=True, capture_output=True, text=True,
    )


@pytest_asyncio.fixture
async def engine(pg_dsn: str) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(pg_dsn, echo=False)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session
