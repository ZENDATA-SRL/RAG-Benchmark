from typing import TypedDict
from uuid import UUID

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from src.config.ingestion.vectordb.service import build_vectordb
from src.config.schemas import RAGConfig, RAGConfigSchema
from src.config.solver.base import BaseSolver
from src.config.solver.prompts import (
    PLANNED_MULTIHOP_EXECUTION_PROMPT,
    PLANNED_MULTIHOP_PLANNING_PROMPT,
)
from src.config.solver.schemas import SolverConfigSchema
from src.core.schemas import Chunk
from src.dataset.models import QuestionORM as Question


class VectorDbSubqueryPlan(BaseModel):
    """Structured output: sub-queries for vector retrieval."""

    queries: list[str] = Field(
        default_factory=list,
        description="List of search queries to run against the vector database.",
    )


class PlannedMultihopState(TypedDict, total=False):
    question: str
    subqueries: list[str]
    answer: str
    chunks: list[Chunk]


class PlannedMultihopSolverResult(TypedDict, total=False):
    answer: str
    chunks: list[Chunk]


def _normalize_message_content(content: object) -> str:
    if isinstance(content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    return str(content)


class PlannedMultihopSolver(BaseSolver):
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
        planner_llm = llm.with_structured_output(VectorDbSubqueryPlan)

        async def planning(state: PlannedMultihopState) -> dict[str, list[str]]:
            prompt = PLANNED_MULTIHOP_PLANNING_PROMPT.format(question=state["question"])
            plan = await planner_llm.ainvoke([HumanMessage(content=prompt)])
            if isinstance(plan, VectorDbSubqueryPlan):
                queries = plan.queries
            elif isinstance(plan, dict):
                raw = plan.get("queries")
                queries = raw if isinstance(raw, list) else []
            else:
                queries = []
            queries = [str(q).strip() for q in queries if str(q).strip()]
            if not queries:
                queries = [state["question"]]
            return {"subqueries": queries}

        async def execution(
            state: PlannedMultihopState,
        ) -> PlannedMultihopSolverResult:
            subqueries = state.get("subqueries") or [state["question"]]
            passages: list[str] = []
            seen: set[str] = set()

            total_chunks: list[Chunk] = []
            rerank = rag_config.solver.reranking or None
            vectordb = build_vectordb(rag_config.vectordb)
            for sub_q in subqueries:
                chunks = await vectordb.retrieve_chunks(
                    embedder=embedder,
                    llm=llm,
                    query=sub_q,
                    top_k=rag_config.solver.top_k,
                    hyde=rag_config.solver.hyde,
                    hybrid=rag_config.solver.hybrid,
                    reranking=rerank,
                    dataset_id=dataset_id,
                    chunker_id=rag_config_record.chunker_id,
                    embedder_id=rag_config_record.embedder_id,
                    ocr_id=rag_config_record.ocr_id,
                )

                for doc in chunks:
                    t = (doc.text or "").strip()
                    if t and t not in seen:
                        total_chunks.append(doc)
                        seen.add(t)
                        passages.append(t)

            context = "\n\n".join(passages)
            prompt = PLANNED_MULTIHOP_EXECUTION_PROMPT.format(
                question=state["question"],
                context=context,
            )
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            text = _normalize_message_content(response.content)
            return {"answer": str(text).strip(), "chunks": total_chunks}

        graph = StateGraph(PlannedMultihopState)
        graph.add_node("planning", planning)
        graph.add_node("execution", execution)
        graph.add_edge(START, "planning")
        graph.add_edge("planning", "execution")
        graph.add_edge("execution", END)

        app = graph.compile()
        final = await app.ainvoke({"question": question.query})
        return final["answer"], final["chunks"]
