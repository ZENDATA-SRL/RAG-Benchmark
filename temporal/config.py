from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from src.infrastructure.temporal import data_converter
from src.settings import Settings, get_settings
from temporalio.converter import DataConverter


def worker_data_converter() -> DataConverter:
    """The data converter every client and worker shares.

    Defined once in `src.infrastructure.temporal` because the API is a Temporal client too:
    the payload size limit of RT-O02 must hold on both sides of the queue.
    """
    return data_converter()


# A dedicated engine for the worker process: activities run their own transaction outside
# any HTTP request, so they must not share the pool `get_session` opens for the API. Built
# lazily so importing this module (for the converter, or in a test) does not open a
# connection.
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _factory() -> async_sessionmaker[AsyncSession]:
    global _engine, _session_factory
    if _session_factory is None:
        settings: Settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            echo=settings.database_echo,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_pre_ping=True,
        )
        _session_factory = async_sessionmaker(
            bind=_engine, expire_on_commit=False, autoflush=False
        )
    return _session_factory


@asynccontextmanager
async def activity_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a session with one transaction per activity, committing on success.

    An activity is its own unit of work: it commits when it returns and rolls back on any
    error, so a failed parse leaves no half-written artefact behind.
    """
    async with _factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_worker_engine() -> None:
    """Close the worker engine's pool at shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
