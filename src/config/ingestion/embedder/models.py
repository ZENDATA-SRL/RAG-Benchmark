from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class EmbeddingConfig(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    provider: str
    model: str
