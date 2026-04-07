from uuid import UUID

from pydantic import BaseModel


class Document(BaseModel):
    id: UUID
    name: str
    path: str


class Question(BaseModel):
    id: UUID


class Benchmark(BaseModel):
    id: UUID
