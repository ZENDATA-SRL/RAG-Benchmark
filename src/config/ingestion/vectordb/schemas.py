from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class VectorDBConfigSchema(BaseModel):
    backend: str = Field(default="chromadb")
    config: dict = Field(default_factory=dict)


class VectorDBConfig(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    backend: str
    config: dict

