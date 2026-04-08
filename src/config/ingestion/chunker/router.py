from uuid import UUID

from fastapi import APIRouter

from config.ingestion.chunker.schemas import ChunkerConfig, ChunkerConfigSchema
from config.ingestion.chunker.service import get_chunker_by_id, resolve_chunker

router = APIRouter(prefix="/config/chunker", tags=["chunker"])


@router.post("/chunker")
async def resolve_chunker_route(chunker: ChunkerConfigSchema) -> ChunkerConfig:
    return await resolve_chunker(chunker)


@router.get("/chunker/{chunker_id}")
async def get_chunker_route(chunker_id: UUID) -> ChunkerConfig:
    return await get_chunker_by_id(chunker_id)
