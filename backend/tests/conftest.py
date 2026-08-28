from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool
from src.settings import Settings, get_settings


@pytest.fixture(scope="session")
def settings() -> Settings:
    """Application settings, read from the same `.env` the app uses."""
    return get_settings()


@pytest_asyncio.fixture
async def engine(settings: Settings) -> AsyncGenerator[AsyncEngine, None]:
    """Engine bound to the dedicated test database.

    Per-test and with `NullPool` on purpose: pytest-asyncio gives each test its own event
    loop, and an asyncpg connection cannot be shared across loops. Pooling here would leak
    a connection from one loop into the next test and fail with "another operation is in
    progress".

    A separate database and not a separate schema: the migration creates PostgreSQL ENUM
    types, which are database-wide, so sharing one with the development data would let a
    test teardown break the dev environment.
    """
    created = create_async_engine(settings.test_database_url, poolclass=NullPool)
    try:
        async with created.connect():
            pass
    except Exception as error:  # pragma: no cover - environment problem, not a test failure
        await created.dispose()
        pytest.skip(f"test database not reachable: {error}")
    yield created
    await created.dispose()


@pytest_asyncio.fixture
async def connection(engine: AsyncEngine) -> AsyncGenerator[AsyncConnection, None]:
    """Open a connection with an outer transaction that is always rolled back."""
    async with engine.connect() as conn:
        transaction = await conn.begin()
        try:
            yield conn
        finally:
            await transaction.rollback()


@pytest_asyncio.fixture
async def session(connection: AsyncConnection) -> AsyncGenerator[AsyncSession, None]:
    """Session joined to the test transaction.

    Everything the test writes is discarded by the outer rollback, so tests neither need
    cleanup code nor see each other's rows, even when the code under test commits: the
    commit only releases the nested transaction, never the outer one.
    """
    factory = async_sessionmaker(bind=connection, expire_on_commit=False, autoflush=False)
    async with factory() as test_session:
        yield test_session


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """`AsyncClient` on the app, with the session dependency bound to the test transaction."""
    from src.infrastructure.database.session import get_session
    from src.main import create_app

    app = create_app()
    # Built without running `lifespan`, so the startup seed does not fire: a test that
    # needs the registry seeds it explicitly and the others start from an empty table.
    app.dependency_overrides[get_session] = lambda: session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client
