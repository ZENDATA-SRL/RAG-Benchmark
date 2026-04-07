from pydantic import BaseModel


class EmbeddingConfigSchema(BaseModel):
    provider: str
    model: str
