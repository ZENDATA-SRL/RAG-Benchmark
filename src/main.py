##
# Core RAG benchmark API: config resolution (RAG, solver, LLM, OCR, chunker, embedder).
##

from fastapi import FastAPI

from config.ingestion.chunker.router import router as chunker_router
from config.ingestion.embedder.router import router as embedder_router
from config.ingestion.ocr.router import router as ocr_router
from config.llms.router import router as llm_router
from config.router import router as rag_config_router
from config.solver.router import router as solver_router

app = FastAPI(title="RAG Benchmark")

app.include_router(rag_config_router)
app.include_router(solver_router)
app.include_router(llm_router)
app.include_router(ocr_router)
app.include_router(chunker_router)
app.include_router(embedder_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
