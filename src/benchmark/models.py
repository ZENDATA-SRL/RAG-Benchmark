from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Document(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    path: str
    url: str
    blob_url: str | None = None
    benchmark_id: UUID


class Question(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    query: str
    answer: str
    document_id: UUID
    benchmark_id: UUID


class Benchmark(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    created_at: datetime
