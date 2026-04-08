from uuid import UUID

from fastapi import APIRouter, HTTPException

from src.config.schemas import RAGConfigSchema
from src.core.process.service import run_process

router = APIRouter(prefix="/core", tags=["core"])


@router.post("/process/{benchmark_id}")
async def run_process_route(benchmark_id: UUID, rag_config: RAGConfigSchema):
    try:
        await run_process(rag_config_schema=rag_config, benchmark_id=benchmark_id)
    except ValueError as e:
        # Currently raised when benchmark does not exist.
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"status": "ok"}

