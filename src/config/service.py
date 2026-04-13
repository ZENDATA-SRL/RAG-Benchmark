import logging
from uuid import UUID

from src.config.ingestion.chunker.service import resolve_chunker
from src.config.ingestion.embedder.service import resolve_embedder
from src.config.ingestion.ocr.service import resolve_ocr
from src.config.ingestion.vectordb.service import resolve_vectordb
from src.config.llms.service import resolve_llm
from src.config.repository import get_rag_repository
from src.config.schemas import RAGConfig, RAGConfigSchema
from src.config.solver.service import resolve_solver

logger = logging.getLogger(__name__)


async def resolve_rag_config(config: RAGConfigSchema) -> RAGConfig:
    repository = get_rag_repository()
    ocr = await resolve_ocr(config.ocr)
    chunker = await resolve_chunker(config.chunker)
    embedder = await resolve_embedder(config.embedder)
    vectordb = await resolve_vectordb(config.vectordb)
    llm = await resolve_llm(config.llm)
    solver = await resolve_solver(config.solver)

    rag_config = await repository.get_rag_config_by_config_and_name(
        name=config.name,
        ocr_id=ocr.id,
        chunker_id=chunker.id,
        embedder_id=embedder.id,
        vectordb_id=vectordb.id,
        llm_id=llm.id,
        solver_id=solver.id,
    )
    if rag_config:
        out = RAGConfig.model_validate(rag_config)
        logger.debug(
            "config.resolve_rag_config.reused",
            extra={
                "event": "config.resolve_rag_config.reused",
                "rag_config_id": str(out.id),
            },
        )
        return out
    rag_config = await repository.insert_rag_config(
        name=config.name,
        ocr_id=ocr.id,
        chunker_id=chunker.id,
        embedder_id=embedder.id,
        vectordb_id=vectordb.id,
        llm_id=llm.id,
        solver_id=solver.id,
    )
    out = RAGConfig.model_validate(rag_config)
    logger.debug(
        "config.resolve_rag_config.inserted",
        extra={
            "event": "config.resolve_rag_config.inserted",
            "rag_config_id": str(out.id),
        },
    )
    return out


async def get_rag_config_by_id(rag_config_id: UUID) -> RAGConfig:
    repository = get_rag_repository()
    obj = await repository.get_rag_config_by_id(rag_config_id)
    if obj is None:
        raise ValueError(f"RAG config {rag_config_id} not found")
    return RAGConfig.model_validate(obj)


async def get_rag_configs() -> list[RAGConfig]:
    repository = get_rag_repository()
    rows = await repository.get_rag_configs()
    return [RAGConfig.model_validate(r) for r in rows]
