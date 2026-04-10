import logging
import os
import threading
from collections.abc import AsyncIterator

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = logging.getLogger(__name__)


def get_database_url() -> str:
    # Allow running via uvicorn without exporting env vars.
    load_dotenv(override=True)
    url = os.getenv("DATABASE_URL")
    if not url:
        logger.error(
            "db.config.missing_database_url",
            extra={"event": "db.config.missing_database_url"},
        )
        raise RuntimeError(
            "DATABASE_URL is not set. Expected something like "
            "'postgresql+asyncpg://user:pass@host:5432/dbname'."
        )
    return url


def create_engine(database_url: str | None = None) -> AsyncEngine:
    return create_async_engine(database_url or get_database_url(), pool_pre_ping=True)


_tls = threading.local()


def get_engine() -> AsyncEngine:
    engine = getattr(_tls, "engine", None)
    if engine is None:
        logger.debug(
            "db.engine.create",
            extra={"event": "db.engine.create", "thread": threading.get_ident()},
        )
        engine = create_engine()
        _tls.engine = engine
    return engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    sm = getattr(_tls, "sessionmaker", None)
    if sm is None:
        logger.debug(
            "db.sessionmaker.create",
            extra={"event": "db.sessionmaker.create", "thread": threading.get_ident()},
        )
        sm = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
        _tls.sessionmaker = sm
    return sm


async def get_db_session() -> AsyncIterator[AsyncSession]:
    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        yield session
