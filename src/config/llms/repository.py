from uuid import UUID

from config.llms.models import LLMConfig
from config.llms.schemas import LLMConfigSchema
from infrastructure.database.db import get_sessionmaker

from sqlalchemy import select


class LLMRepository:
    async def get_llm_by_id(self, llm_id: UUID) -> LLMConfig | None:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as session:
            return await session.get(LLMConfig, llm_id)

    async def get_llm_by_config(self, llm: LLMConfigSchema) -> LLMConfig | None:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as session:
            stmt = (
                select(LLMConfig)
                .where(LLMConfig.provider == llm.provider)
                .where(LLMConfig.model == llm.model)
                .limit(1)
            )
            return await session.scalar(stmt)

    async def insert_llm_config(self, llm: LLMConfigSchema) -> LLMConfig:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as session:
            obj = LLMConfig(provider=llm.provider, model=llm.model)
            session.add(obj)
            await session.commit()
            await session.refresh(obj)
            return obj


def get_llm_repository() -> LLMRepository:
    return LLMRepository()
