from typing import List
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Scan(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    ocr_id: UUID
    text: str
    document_id: UUID


class Chunk(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    scan_id: UUID
    chunker_id: UUID
    start_index: int
    end_index: int
    text: str


class Embedding(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    vectors: List[float]
    text: str
    embedder_id: UUID
    chunk_id: UUID
