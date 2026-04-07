from pydantic import BaseModel

from config.ingestion.chunker.schemas import ChunkerConfigSchema
from config.ingestion.embedder.schemas import EmbeddingConfigSchema
from config.ingestion.ocr.schemas import OCRConfigSchema
from config.llms.schemas import LLMConfigSchema
from config.solver.schemas import SolverConfigSchema


class RAGConfigSchema(BaseModel):
    ocr: OCRConfigSchema
    chunker: ChunkerConfigSchema
    embedder: EmbeddingConfigSchema
    llm: LLMConfigSchema
    solver: SolverConfigSchema
