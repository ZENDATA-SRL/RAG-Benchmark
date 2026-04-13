from uuid import UUID

from sqlalchemy import select

from src.config.ingestion.vectordb.models import VectorDBConfigORM
from src.config.ingestion.vectordb.schemas import VectorDBConfigSchema
from src.infrastructure.database.db import get_sessionmaker


class VectorDBRepository:
    async def get_vectordb_by_id(self, vectordb_id: UUID) -> VectorDBConfigORM | None:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as session:
            return await session.get(VectorDBConfigORM, vectordb_id)

    async def get_vectordb_by_config(
        self, vectordb: VectorDBConfigSchema
    ) -> VectorDBConfigORM | None:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as session:
            stmt = (
                select(VectorDBConfigORM)
                .where(VectorDBConfigORM.backend == vectordb.backend)
                .where(VectorDBConfigORM.config == vectordb.config)
                .limit(1)
            )
            return await session.scalar(stmt)

    async def insert_vectordb_config(
        self, vectordb: VectorDBConfigSchema
    ) -> VectorDBConfigORM:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as session:
            obj = VectorDBConfigORM(backend=vectordb.backend, config=vectordb.config)
            session.add(obj)
            await session.commit()
            await session.refresh(obj)
            return obj


def get_vectordb_repository() -> VectorDBRepository:
    return VectorDBRepository()

