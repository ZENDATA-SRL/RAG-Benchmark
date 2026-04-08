from uuid import UUID

from pydantic import BaseModel, ConfigDict

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


class RAGConfig(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ocr_id: UUID
    chunker_id: UUID
    embedder_id: UUID
    llm_id: UUID
    solver_id: UUID
