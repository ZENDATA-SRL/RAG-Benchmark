from uuid import UUID

from fastapi import APIRouter

from config.ingestion.embedder.schemas import EmbeddingConfigSchema
from config.ingestion.embedder.service import get_embedder_by_id, resolve_embedder

router = APIRouter(prefix="/config/embedder", tags=["embedder"])


@router.post("/embedder")
async def resolve_embedder_route(embedder: EmbeddingConfigSchema):
    return await resolve_embedder(embedder)


@router.get("/embedder/{embedder_id}")
async def get_embedder_route(embedder_id: UUID):
    return await get_embedder_by_id(embedder_id)
