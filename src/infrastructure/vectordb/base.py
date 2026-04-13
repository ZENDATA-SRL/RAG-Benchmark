from abc import ABC, abstractmethod
from typing import Literal
from uuid import UUID

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel

from src.infrastructure.vectordb.models import EmbeddedChunk


class BaseVectorDB(ABC):
    @abstractmethod
    async def retrieve_chunks(
        self,
        *,
        embedder: Embeddings,
        llm: BaseChatModel,
        query: str,
        top_k: int,
        hyde: bool,
        hybrid: bool,
        reranking: Literal["llm", "semantic"] | None,
        dataset_id: UUID,
        chunker_id: UUID,
        embedder_id: UUID,
        ocr_id: UUID,
    ) -> list[EmbeddedChunk]:
        raise NotImplementedError

    @abstractmethod
    async def upload_chunks(self, *, chunks: list[EmbeddedChunk], embedder: Embeddings) -> None:
        raise NotImplementedError

