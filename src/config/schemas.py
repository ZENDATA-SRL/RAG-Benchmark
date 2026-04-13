from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.config.ingestion.chunker.schemas import ChunkerConfigSchema
from src.config.ingestion.embedder.schemas import EmbeddingConfigSchema
from src.config.ingestion.ocr.schemas import OCRConfigSchema
from src.config.ingestion.vectordb.schemas import VectorDBConfigSchema
from src.config.llms.schemas import LLMConfigSchema
from src.config.solver.schemas import SolverConfigSchema


class RAGConfigSchema(BaseModel):
    # Human-friendly label for the resolved/persisted config.
    name: str
    ocr: OCRConfigSchema
    chunker: ChunkerConfigSchema
    embedder: EmbeddingConfigSchema
    vectordb: VectorDBConfigSchema = Field(default_factory=VectorDBConfigSchema)
    llm: LLMConfigSchema
    solver: SolverConfigSchema


class RAGConfig(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    ocr_id: UUID
    chunker_id: UUID
    embedder_id: UUID
    vectordb_id: UUID
    llm_id: UUID
    solver_id: UUID
