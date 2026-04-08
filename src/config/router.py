from uuid import UUID

from fastapi import APIRouter

from config.schemas import RAGConfigSchema
from config.service import get_rag_config_by_id, resolve_rag_config

router = APIRouter(prefix="/config", tags=["config"])


@router.post("/rag")
async def resolve_rag_config_route(rag_config: RAGConfigSchema):
    return await resolve_rag_config(rag_config)


@router.get("/rag/{rag_config_id}")
async def get_rag_config_route(rag_config_id: UUID):
    return await get_rag_config_by_id(rag_config_id)
