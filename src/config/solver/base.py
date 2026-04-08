from abc import ABC, abstractmethod

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel

from src.dataset.models import QuestionORM as Question
from config.solver.schemas import SolverConfigSchema


class BaseSolver(ABC):

    @abstractmethod 
    async def answer_question(self, question: Question, llm: BaseChatModel, embedder: Embeddings, solver_config: SolverConfigSchema) -> str:
        pass
    
