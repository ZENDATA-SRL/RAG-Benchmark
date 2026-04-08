##
# Core RAG dataset API: config resolution (RAG, solver, LLM, OCR, chunker, embedder).
##

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.dataset.router import router as dataset_router
from src.config.router import router as config_router
from src.core.router import router as core_router

app = FastAPI(title="RAG Dataset")

app.include_router(config_router)
app.include_router(dataset_router)
app.include_router(core_router)


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
