from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ChunkerConfig(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    strategy: str = Field(default="")
    chunk_size: int = Field(default=1000)
    overlap_size: int = Field(default=0)
