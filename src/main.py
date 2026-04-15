##
# Core RAG dataset API: config resolution (RAG, solver, LLM, OCR, chunker, embedder).
##

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import src.infrastructure.database.models as _orm_models  # noqa: F401
from src.config.router import router as config_router
from src.core.router import router as core_router
from src.dataset.router import router as dataset_router
from src.evals.router import router as evals_router
from src.infrastructure.langfuse_client import shutdown_langfuse_client
from src.infrastructure.logging_config import configure_logging

configure_logging()


@asynccontextmanager
async def lifespan(_: FastAPI):
    """
    Ensure external clients close cleanly on shutdown/reload.

    This prevents "Task exception was never retrieved" / "Event loop is closed"
    warnings from late HTTP client finalizers when running with `uvicorn --reload`.
    """

    yield

    try:
        shutdown_langfuse_client()
    except Exception:
        # Best-effort cleanup; shutdown should not block app exit.
        pass


app = FastAPI(title="RAG Dataset", lifespan=lifespan)

app.include_router(config_router)
app.include_router(dataset_router)
app.include_router(core_router)
app.include_router(evals_router)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # es. ["http://localhost:3000"]
    allow_credentials=True,
    allow_methods=["*"],  # o ["GET","POST",...]
    allow_headers=["*"],  # o lista specifica (Authorization, Content-Type, ...)
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
