from uuid import UUID

from src.config.llms.models import LLMConfigORM
from src.config.llms.schemas import LLMConfigSchema
from src.infrastructure.database.db import get_sessionmaker

from sqlalchemy import select


class LLMRepository:
    async def get_llm_by_id(self, llm_id: UUID) -> LLMConfigORM | None:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as session:
            return await session.get(LLMConfigORM, llm_id)

    async def get_llm_by_config(self, llm: LLMConfigSchema) -> LLMConfigORM | None:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as session:
            stmt = (
                select(LLMConfigORM)
                .where(LLMConfigORM.provider == llm.provider)
                .where(LLMConfigORM.model == llm.model)
                .limit(1)
            )
            return await session.scalar(stmt)

    async def insert_llm_config(self, llm: LLMConfigSchema) -> LLMConfigORM:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as session:
            obj = LLMConfigORM(provider=llm.provider, model=llm.model)
            session.add(obj)
            await session.commit()
            await session.refresh(obj)
            return obj


def get_llm_repository() -> LLMRepository:
    return LLMRepository()
