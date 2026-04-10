from datetime import datetime
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
    vectors: list[float]


class Experiment(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dataset_id: UUID
    ragconfig_id: UUID
    name: str
    dataset_run_id: str | None = None
    langfuse_experiment_id: str | None = None
    created_at: datetime


class Answer(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    experiment_id: UUID
    question_id: UUID
    answer: str


class AnswerChunk(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    answer_id: UUID
    chunk_id: UUID
    text: str
