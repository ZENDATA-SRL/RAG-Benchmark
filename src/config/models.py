from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class RAGConfig(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    ocr_id: UUID = Field(default_factory=uuid4)
    chunker_id: UUID = Field(default_factory=uuid4)
    embedder_id: UUID = Field(default_factory=uuid4)
    llm_id: UUID = Field(default_factory=uuid4)
    solver_id: UUID = Field(default_factory=uuid4)
