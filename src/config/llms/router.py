from uuid import UUID

from fastapi import APIRouter

from config.llms.schemas import LLMConfig, LLMConfigSchema
from config.llms.service import get_llm_by_id, resolve_llm

router = APIRouter(prefix="/config/llm", tags=["llm"])


@router.post("/llm")
async def resolve_llm_route(llm: LLMConfigSchema) -> LLMConfig:
    return await resolve_llm(llm)


@router.get("/llm/{llm_id}")
async def get_llm_route(llm_id: UUID) -> LLMConfig:
    return await get_llm_by_id(llm_id)
