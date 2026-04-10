from uuid import UUID

from langchain.embeddings import init_embeddings
from langchain_core.embeddings import Embeddings

from src.config.ingestion.embedder.repository import get_embedder_repository
from src.config.ingestion.embedder.schemas import EmbeddingConfig, EmbeddingConfigSchema


def build_embedder(embedder_config: EmbeddingConfigSchema) -> Embeddings:
    return init_embeddings(
        model=embedder_config.model, provider=embedder_config.provider
    )


async def resolve_embedder(embedder: EmbeddingConfigSchema) -> EmbeddingConfig:
    repository = get_embedder_repository()
    embedder_object = await repository.get_embedder_by_config(embedder)
    if embedder_object:
        return EmbeddingConfig.model_validate(embedder_object)
    created = await repository.insert_embedder_config(embedder)
    return EmbeddingConfig.model_validate(created)


async def get_embedder_by_id(embedder_id: UUID) -> EmbeddingConfig:
    repository = get_embedder_repository()
    obj = await repository.get_embedder_by_id(embedder_id)
    if obj is None:
        raise ValueError(f"Embedder config {embedder_id} not found")
    return EmbeddingConfig.model_validate(obj)
