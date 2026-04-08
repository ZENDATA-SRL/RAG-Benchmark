from uuid import UUID

from config.ingestion.chunker.models import ChunkerConfigORM
from config.ingestion.chunker.schemas import ChunkerConfigSchema
from infrastructure.database.db import get_sessionmaker

from sqlalchemy import select


class ChunkerRepository:
    async def get_chunker_by_id(self, chunker_id: UUID) -> ChunkerConfigORM | None:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as session:
            return await session.get(ChunkerConfigORM, chunker_id)

    async def get_chunker_by_config(
        self, chunker: ChunkerConfigSchema
    ) -> ChunkerConfigORM | None:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as session:
            stmt = (
                select(ChunkerConfigORM)
                .where(ChunkerConfigORM.strategy == chunker.strategy)
                .where(ChunkerConfigORM.chunk_size == chunker.chunk_size)
                .where(ChunkerConfigORM.overlap_size == chunker.overlap_size)
                .limit(1)
            )
            return await session.scalar(stmt)

    async def insert_chunker_config(self, chunker: ChunkerConfigSchema) -> ChunkerConfigORM:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as session:
            obj = ChunkerConfigORM(
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
