from uuid import UUID

from pydantic import BaseModel, ConfigDict


class OCRConfigSchema(BaseModel):
    model: str


class OCRConfig(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    model: str
