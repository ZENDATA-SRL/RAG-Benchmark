from uuid import UUID

from fastapi import APIRouter

from src.config.ingestion.chunker.schemas import ChunkerConfig, ChunkerConfigSchema
from src.config.ingestion.chunker.service import get_chunker_by_id, resolve_chunker

router = APIRouter(prefix="/chunker", tags=["chunker"])


@router.post("")
async def resolve_chunker_route(chunker: ChunkerConfigSchema) -> ChunkerConfig:
    return await resolve_chunker(chunker)


@router.get("/{chunker_id}")
async def get_chunker_route(chunker_id: UUID) -> ChunkerConfig:
    return await get_chunker_by_id(chunker_id)
