from abc import ABC, abstractmethod
from uuid import UUID

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel

from src.config.schemas import RAGConfig, RAGConfigSchema
from src.core.schemas import Chunk
from src.dataset.models import QuestionORM as Question


class BaseSolver(ABC):
    @abstractmethod
    async def answer_question(
        self,
        question: Question,
        llm: BaseChatModel,
        embedder: Embeddings,
        rag_config: RAGConfigSchema,
        dataset_id: UUID,
        rag_config_record: RAGConfig,
    ) -> tuple[str, list[Chunk]]:
        pass
