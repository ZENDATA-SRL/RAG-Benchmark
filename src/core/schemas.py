from uuid import UUID

from pydantic import BaseModel, ConfigDict


class Scan(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ocr_id: UUID
    document_id: UUID
    text: str


class Chunk(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    scan_id: UUID
    chunker_id: UUID
    start_index: int
    end_index: int
    text: str


class Embedding(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    chunk_id: UUID
    embedder_id: UUID
    text: str
    vectors: list[float]

