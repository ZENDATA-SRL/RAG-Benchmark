from uuid import UUID

from config.models import RAGConfig


class RAGRepository:
    async def get_rag_config_by_config(
        self,
        ocr_id: UUID,
        chunker_id: UUID,
        embedder_id: UUID,
        llm_id: UUID,
        solver_id: UUID,
    ) -> RAGConfig | None:
        pass

    async def get_rag_config(self, config_id: UUID) -> RAGConfig | None:
        pass

    async def insert_rag_config(
        self,
        ocr_id: UUID,
        chunker_id: UUID,
        embedder_id: UUID,
        llm_id: UUID,
        solver_id: UUID,
    ) -> RAGConfig:
        pass


def get_rag_repository() -> RAGRepository:
    return RAGRepository()
