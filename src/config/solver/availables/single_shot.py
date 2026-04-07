
from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage

from benchmark.models import Question
from config.solver.base import BaseSolver
from config.solver.prompts import ONESHOT_SOLVER_PROMPT
from config.solver.schemas import SolverConfigSchema
from infrastructure.vectordb.azure_search import retrieve_chunks


class OneShotSolver(BaseSolver):
    async def answer_question(
        self,
        question: Question,
        llm: BaseChatModel,
        embedder: Embeddings,
        solver_config: SolverConfigSchema,
    ) -> str:
        # qui costruisco il filtro per il vector db (solo chunks provenienti da documenti del benchmark gestiti con il chunker, l'embedder e l'ocr configurati)
        # Potrebbe convenire cambiare l'intero modello inserendoci questi campi anche se ridondante.

        chunks = retrieve_chunks(
            question.query,
            solver_config.top_k,
            solver_config.reranking,
            solver_config.hybrid, 
            embedder
        )

        passages: list[str] = []
        for doc in chunks:
            if isinstance(doc, dict):
                key = "azuz" #TODO: Devo cambiare il tipo di doc in base a come ho configurato il vector db
                text = doc.get(key)
                if isinstance(text, str) and text.strip():
                    passages.append(text.strip())
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

        
        return str(text).strip()
