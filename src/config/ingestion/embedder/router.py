from uuid import UUID

from fastapi import APIRouter

from src.config.ingestion.embedder.schemas import EmbeddingConfig, EmbeddingConfigSchema
from src.config.ingestion.embedder.service import get_embedder_by_id, resolve_embedder

router = APIRouter(prefix="/embedder", tags=["embedder"])


@router.post("")
async def resolve_embedder_route(embedder: EmbeddingConfigSchema) -> EmbeddingConfig:
    return await resolve_embedder(embedder)


@router.get("/{embedder_id}")
async def get_embedder_route(embedder_id: UUID) -> EmbeddingConfig:
    return await get_embedder_by_id(embedder_id)
