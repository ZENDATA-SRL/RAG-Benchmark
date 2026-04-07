from pydantic import BaseModel


class OCRConfigSchema(BaseModel):
    model: str
