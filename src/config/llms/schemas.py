from pydantic import BaseModel


class LLMConfigSchema(BaseModel):
    provider: str
    model: str
