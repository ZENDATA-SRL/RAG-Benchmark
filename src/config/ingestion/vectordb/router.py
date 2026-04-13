from uuid import UUID

from fastapi import APIRouter

from src.config.ingestion.vectordb.schemas import VectorDBConfig, VectorDBConfigSchema
from src.config.ingestion.vectordb.service import get_vectordb_by_id, resolve_vectordb

router = APIRouter(prefix="/vectordb", tags=["vectordb"])


@router.post("")
async def resolve_vectordb_route(vectordb: VectorDBConfigSchema) -> VectorDBConfig:
    return await resolve_vectordb(vectordb)


@router.get("/{vectordb_id}")
async def get_vectordb_route(vectordb_id: UUID) -> VectorDBConfig:
    return await get_vectordb_by_id(vectordb_id)

