from uuid import UUID

from pydantic import BaseModel, Field


class EmbeddedChunk(BaseModel):
    """
    Canonical payload stored/retrieved from vector DB.

    `id` is the identifier used inside the vector DB. We use the embedding row id
    so it's stable and unique per (chunk, embedder) pair.
    """

    id: UUID
    chunk_id: UUID
    embedding_id: UUID
    text: str
    vectors: list[float] = Field(default_factory=list)

