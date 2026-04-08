from uuid import UUID

from config.models import RAGConfigORM
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
    ) -> RAGConfigORM | None:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as session:
            stmt = (
                select(RAGConfigORM)
                .where(RAGConfigORM.ocr_id == ocr_id)
                .where(RAGConfigORM.chunker_id == chunker_id)
                .where(RAGConfigORM.embedder_id == embedder_id)
                .where(RAGConfigORM.llm_id == llm_id)
                .where(RAGConfigORM.solver_id == solver_id)
                .limit(1)
            )
            return await session.scalar(stmt)

    async def get_rag_config_by_id(self, rag_config_id: UUID) -> RAGConfigORM | None:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as session:
            return await session.get(RAGConfigORM, rag_config_id)

    async def insert_rag_config(
        self,
        ocr_id: UUID,
        chunker_id: UUID,
        embedder_id: UUID,
        llm_id: UUID,
        solver_id: UUID,
    ) -> RAGConfigORM:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as session:
            obj = RAGConfigORM(
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
