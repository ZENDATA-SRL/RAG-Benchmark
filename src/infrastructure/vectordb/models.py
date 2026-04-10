from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class EmbeddedChunk(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    chunk_id: UUID
    embedding_id: UUID
    text: str
    vectors: list[float]
