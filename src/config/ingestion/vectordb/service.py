from uuid import UUID

from src.config.ingestion.vectordb.repository import get_vectordb_repository
from src.config.ingestion.vectordb.schemas import VectorDBConfig, VectorDBConfigSchema
from src.infrastructure.vectordb.azure_search import AzureSearchVectorDB
from src.infrastructure.vectordb.base import BaseVectorDB
from src.infrastructure.vectordb.chromadb import ChromaVectorDB


def build_vectordb(vectordb_config: VectorDBConfigSchema) -> BaseVectorDB:
    backend = (vectordb_config.backend or "").strip().lower()
    if backend in ("chroma", "chromadb"):
        return ChromaVectorDB(vectordb_config)
    if backend in ("azure", "azure_search", "azure-ai-search"):
        return AzureSearchVectorDB(vectordb_config)
    raise ValueError(f"Unknown vector DB backend: {vectordb_config.backend}")


async def resolve_vectordb(vectordb: VectorDBConfigSchema) -> VectorDBConfig:
    repository = get_vectordb_repository()
    obj = await repository.get_vectordb_by_config(vectordb)
    if obj:
        return VectorDBConfig.model_validate(obj)
    created = await repository.insert_vectordb_config(vectordb)
    return VectorDBConfig.model_validate(created)


async def get_vectordb_by_id(vectordb_id: UUID) -> VectorDBConfig:
    repository = get_vectordb_repository()
    obj = await repository.get_vectordb_by_id(vectordb_id)
    if obj is None:
        raise ValueError(f"Vector DB config {vectordb_id} not found")
    return VectorDBConfig.model_validate(obj)