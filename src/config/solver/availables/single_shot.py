from uuid import UUID

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage

from src.config.schemas import RAGConfig, RAGConfigSchema
from src.config.solver.base import BaseSolver
from src.config.solver.prompts import ONESHOT_SOLVER_PROMPT
from src.config.solver.schemas import SolverConfigSchema
from src.core.schemas import Chunk
from src.dataset.models import QuestionORM as Question
from src.config.ingestion.vectordb.service import build_vectordb


class OneShotSolver(BaseSolver):
    def __init__(self, solver_config: SolverConfigSchema) -> None:
        self._solver_config = solver_config

    async def answer_question(
        self,
        question: Question,
        llm: BaseChatModel,
        embedder: Embeddings,
        rag_config: RAGConfigSchema,
        dataset_id: UUID,
        rag_config_record: RAGConfig,
    ) -> tuple[str, list[Chunk]]:
        rerank = rag_config.solver.reranking or None
        vectordb = build_vectordb(rag_config.vectordb)
        chunks = await vectordb.retrieve_chunks(
            embedder=embedder,
            llm=llm,
            query=question.query,
            top_k=rag_config.solver.top_k,
            hyde=rag_config.solver.hyde,
            hybrid=rag_config.solver.hybrid,
            reranking=rerank,
            dataset_id=dataset_id,
            chunker_id=rag_config_record.chunker_id,
            embedder_id=rag_config_record.embedder_id,
            ocr_id=rag_config_record.ocr_id,
        )

        passages: list[str] = []
        for doc in chunks:
            t = (doc.text or "").strip()
            if t:
                passages.append(t)
                break

        context = "\n\n".join(passages)
        prompt = ONESHOT_SOLVER_PROMPT.format(question=question.query, context=context)
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        text = response.content
        if isinstance(text, list):
            text = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in text
            )

        return str(text).strip(), chunks
