from uuid import UUID

from pydantic import BaseModel, ConfigDict


class EmbeddingConfigSchema(BaseModel):
    provider: str
    model: str


class EmbeddingConfig(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider: str
    model: str
