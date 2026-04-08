from uuid import UUID

from config.ingestion.chunker.models import ChunkerConfig
from config.ingestion.chunker.schemas import ChunkerConfigSchema
from infrastructure.database.db import get_sessionmaker

from sqlalchemy import select


class ChunkerRepository:
    async def get_chunker_by_id(self, chunker_id: UUID) -> ChunkerConfig | None:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as session:
            return await session.get(ChunkerConfig, chunker_id)

    async def get_chunker_by_config(
        self, chunker: ChunkerConfigSchema
    ) -> ChunkerConfig | None:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as session:
            stmt = (
                select(ChunkerConfig)
                .where(ChunkerConfig.strategy == chunker.strategy)
                .where(ChunkerConfig.chunk_size == chunker.chunk_size)
                .where(ChunkerConfig.overlap_size == chunker.overlap_size)
                .limit(1)
            )
            return await session.scalar(stmt)

    async def insert_chunker_config(self, chunker: ChunkerConfigSchema) -> ChunkerConfig:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as session:
            obj = ChunkerConfig(
                strategy=chunker.strategy,
                chunk_size=chunker.chunk_size,
                overlap_size=chunker.overlap_size,
            )
            session.add(obj)
            await session.commit()
            await session.refresh(obj)
            return obj


def get_chunker_repository() -> ChunkerRepository:
    return ChunkerRepository()
