from uuid import UUID

from src.config.ingestion.chunker.service import resolve_chunker
from src.config.ingestion.embedder.service import resolve_embedder
from src.config.ingestion.ocr.service import resolve_ocr
from src.config.llms.service import resolve_llm
from src.config.repository import get_rag_repository
from src.config.schemas import RAGConfig, RAGConfigSchema
from src.config.solver.service import resolve_solver


async def resolve_rag_config(config: RAGConfigSchema) -> RAGConfig:
    repository = get_rag_repository()
    ocr = await resolve_ocr(config.ocr)
    chunker = await resolve_chunker(config.chunker)
    embedder = await resolve_embedder(config.embedder)
    llm = await resolve_llm(config.llm)
    solver = await resolve_solver(config.solver)

    rag_config = await repository.get_rag_config_by_config(
        ocr_id=ocr.id,
        chunker_id=chunker.id,
        embedder_id=embedder.id,
        llm_id=llm.id,
        solver_id=solver.id,
    )
    if rag_config:
        return RAGConfig.model_validate(rag_config)
    rag_config = await repository.insert_rag_config(
        ocr_id=ocr.id,
        chunker_id=chunker.id,
        embedder_id=embedder.id,
        llm_id=llm.id,
        solver_id=solver.id,
    )
    return RAGConfig.model_validate(rag_config)


async def get_rag_config_by_id(rag_config_id: UUID) -> RAGConfig:
    repository = get_rag_repository()
    obj = await repository.get_rag_config_by_id(rag_config_id)
    if obj is None:
        raise ValueError(f"RAG config {rag_config_id} not found")
    return RAGConfig.model_validate(obj)
