from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ChunkerConfigSchema(BaseModel):
    strategy: str = Field(default="")
    chunk_size: int = Field(default=1000)
    overlap_size: int = Field(default=0)


class ChunkerConfig(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    strategy: str
    chunk_size: int
    overlap_size: int
