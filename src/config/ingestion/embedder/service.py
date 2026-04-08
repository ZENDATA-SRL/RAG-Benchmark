from uuid import UUID

from langchain.embeddings import init_embeddings
from langchain_core.embeddings import Embeddings

from config.ingestion.embedder.models import EmbeddingConfig
from config.ingestion.embedder.repository import get_embedder_repository
from config.ingestion.embedder.schemas import EmbeddingConfigSchema


def build_embedder(embedder_config: EmbeddingConfigSchema) -> Embeddings:
    return init_embeddings(
        model=embedder_config.model, model_provider=embedder_config.provider
    )


async def resolve_embedder(embedder: EmbeddingConfigSchema) -> EmbeddingConfig:
    repository = get_embedder_repository()
    embedder_object = await repository.get_embedder_by_config(embedder)
    if embedder_object:
        return embedder_object
    return await repository.insert_embedder_config(embedder)


async def get_embedder_by_id(embedder_id: UUID) -> EmbeddingConfig:
    repository = get_embedder_repository()
    return await repository.get_embedder_by_id(embedder_id)
