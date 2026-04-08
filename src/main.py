##
# Core RAG benchmark API: config resolution (RAG, solver, LLM, OCR, chunker, embedder).
##

from fastapi import FastAPI

from src.benchmark.router import router as benchmark_router
from src.config.router import router as config_router
from src.core.router import router as core_router

app = FastAPI(title="RAG Benchmark")

app.include_router(config_router)
app.include_router(benchmark_router)
app.include_router(core_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
