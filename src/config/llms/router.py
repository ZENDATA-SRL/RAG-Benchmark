from uuid import UUID

from fastapi import APIRouter

from src.config.llms.schemas import LLMConfig, LLMConfigSchema
from src.config.llms.service import get_llm_by_id, resolve_llm

router = APIRouter(prefix="/llm", tags=["llm"])


@router.post("")
async def resolve_llm_route(llm: LLMConfigSchema) -> LLMConfig:
    return await resolve_llm(llm)


@router.get("/{llm_id}")
async def get_llm_route(llm_id: UUID) -> LLMConfig:
    return await get_llm_by_id(llm_id)
