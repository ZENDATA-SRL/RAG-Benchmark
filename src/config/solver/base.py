from abc import ABC, abstractmethod

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel

from src.config.solver.schemas import SolverConfigSchema
from src.core.schemas import Chunk
from src.dataset.models import QuestionORM as Question


class BaseSolver(ABC):
    @abstractmethod
    async def answer_question(
        self,
        question: Question,
        llm: BaseChatModel,
        embedder: Embeddings,
        solver_config: SolverConfigSchema,
    ) -> tuple[str, list[Chunk]]:
        pass
