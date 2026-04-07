from config.ingestion.embedder.models import EmbeddingConfig
from config.ingestion.embedder.schemas import EmbeddingConfigSchema


class EmbedderRepository:
    async def get_embedder_by_config(
        self, embedder: EmbeddingConfigSchema
    ) -> EmbeddingConfig | None:
        pass

    async def insert_embedder_config(
        self, embedder: EmbeddingConfigSchema
    ) -> EmbeddingConfig:
        pass


def get_embedder_repository() -> EmbedderRepository:
    return EmbedderRepository()
