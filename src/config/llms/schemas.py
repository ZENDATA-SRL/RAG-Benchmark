from uuid import UUID

from pydantic import BaseModel, ConfigDict


class LLMConfigSchema(BaseModel):
    provider: str
    model: str


class LLMConfig(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider: str
    model: str
