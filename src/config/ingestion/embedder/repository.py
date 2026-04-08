from uuid import UUID

from config.ingestion.embedder.models import EmbeddingConfig
from config.ingestion.embedder.schemas import EmbeddingConfigSchema
from infrastructure.database.db import get_sessionmaker

from sqlalchemy import select


class EmbedderRepository:
    async def get_embedder_by_id(self, embedder_id: UUID) -> EmbeddingConfig | None:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as session:
            return await session.get(EmbeddingConfig, embedder_id)

    async def get_embedder_by_config(
        self, embedder: EmbeddingConfigSchema
    ) -> EmbeddingConfig | None:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as session:
            stmt = (
                select(EmbeddingConfig)
                .where(EmbeddingConfig.provider == embedder.provider)
                .where(EmbeddingConfig.model == embedder.model)
                .limit(1)
            )
            return await session.scalar(stmt)

    async def insert_embedder_config(
        self, embedder: EmbeddingConfigSchema
    ) -> EmbeddingConfig:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as session:
            obj = EmbeddingConfig(provider=embedder.provider, model=embedder.model)
            session.add(obj)
            await session.commit()
            await session.refresh(obj)
            return obj


def get_embedder_repository() -> EmbedderRepository:
    return EmbedderRepository()
