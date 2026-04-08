from uuid import UUID

from fastapi import APIRouter

from config.ingestion.embedder.schemas import EmbeddingConfig, EmbeddingConfigSchema
from config.ingestion.embedder.service import get_embedder_by_id, resolve_embedder

router = APIRouter(prefix="/config/embedder", tags=["embedder"])


@router.post("/embedder")
async def resolve_embedder_route(embedder: EmbeddingConfigSchema) -> EmbeddingConfig:
    return await resolve_embedder(embedder)


@router.get("/embedder/{embedder_id}")
async def get_embedder_route(embedder_id: UUID) -> EmbeddingConfig:
    return await get_embedder_by_id(embedder_id)
