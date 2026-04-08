from uuid import UUID

from config.models import RAGConfig
from infrastructure.database.db import get_sessionmaker

from sqlalchemy import select


class RAGRepository:
    async def get_rag_config_by_config(
        self,
        ocr_id: UUID,
        chunker_id: UUID,
        embedder_id: UUID,
        llm_id: UUID,
        solver_id: UUID,
    ) -> RAGConfig | None:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as session:
            stmt = (
                select(RAGConfig)
                .where(RAGConfig.ocr_id == ocr_id)
                .where(RAGConfig.chunker_id == chunker_id)
                .where(RAGConfig.embedder_id == embedder_id)
                .where(RAGConfig.llm_id == llm_id)
                .where(RAGConfig.solver_id == solver_id)
                .limit(1)
            )
            return await session.scalar(stmt)

    async def get_rag_config_by_id(self, rag_config_id: UUID) -> RAGConfig | None:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as session:
            return await session.get(RAGConfig, rag_config_id)

    async def insert_rag_config(
        self,
        ocr_id: UUID,
        chunker_id: UUID,
        embedder_id: UUID,
        llm_id: UUID,
        solver_id: UUID,
    ) -> RAGConfig:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as session:
            obj = RAGConfig(
                ocr_id=ocr_id,
                chunker_id=chunker_id,
                embedder_id=embedder_id,
                llm_id=llm_id,
                solver_id=solver_id,
            )
            session.add(obj)
            await session.commit()
            await session.refresh(obj)
            return obj


def get_rag_repository() -> RAGRepository:
    return RAGRepository()
