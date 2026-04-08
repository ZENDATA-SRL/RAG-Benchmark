from uuid import UUID

from fastapi import APIRouter

from src.config.ingestion.chunker.router import router as chunker_router
from src.config.ingestion.embedder.router import router as embedder_router
from src.config.ingestion.ocr.router import router as ocr_router
from src.config.llms.router import router as llm_router
from src.config.schemas import RAGConfig, RAGConfigSchema
from src.config.service import get_rag_config_by_id, resolve_rag_config
from src.config.solver.router import router as solver_router

router = APIRouter(prefix="/config", tags=["config"])


@router.post("/rag")
async def resolve_rag_config_route(rag_config: RAGConfigSchema) -> RAGConfig:
    return await resolve_rag_config(rag_config)


@router.get("/rag/{rag_config_id}")
async def get_rag_config_route(rag_config_id: UUID) -> RAGConfig:
    return await get_rag_config_by_id(rag_config_id)


# Mount config sub-routers under the /config namespace.
router.include_router(solver_router)
router.include_router(llm_router)
router.include_router(ocr_router)
router.include_router(chunker_router)
router.include_router(embedder_router)
