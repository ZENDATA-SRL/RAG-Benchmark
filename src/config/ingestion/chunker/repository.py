from config.ingestion.chunker.models import ChunkerConfig
from config.ingestion.chunker.schemas import ChunkerConfigSchema


class ChunkerRepository:
    async def get_chunker_by_config(
        self, chunker: ChunkerConfigSchema
    ) -> ChunkerConfig | None:
        pass

    async def insert_chunker_config(self, chunker: ChunkerConfigSchema) -> ChunkerConfig:
        pass


def get_chunker_repository() -> ChunkerRepository:
    return ChunkerRepository()
