from uuid import UUID

from sqlalchemy import select

from src.config.ingestion.embedder.models import EmbeddingConfigORM
from src.config.ingestion.embedder.schemas import EmbeddingConfigSchema
from src.infrastructure.database.db import get_sessionmaker


class EmbedderRepository:
    async def get_embedder_by_id(self, embedder_id: UUID) -> EmbeddingConfigORM | None:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as session:
            return await session.get(EmbeddingConfigORM, embedder_id)

    async def get_embedder_by_config(
        self, embedder: EmbeddingConfigSchema
    ) -> EmbeddingConfigORM | None:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as session:
            stmt = (
                select(EmbeddingConfigORM)
                .where(EmbeddingConfigORM.provider == embedder.provider)
                .where(EmbeddingConfigORM.model == embedder.model)
                .limit(1)
            )
            return await session.scalar(stmt)

    async def insert_embedder_config(
        self, embedder: EmbeddingConfigSchema
    ) -> EmbeddingConfigORM:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as session:
            obj = EmbeddingConfigORM(provider=embedder.provider, model=embedder.model)
            session.add(obj)
            await session.commit()
            await session.refresh(obj)
            return obj


def get_embedder_repository() -> EmbedderRepository:
    return EmbedderRepository()
