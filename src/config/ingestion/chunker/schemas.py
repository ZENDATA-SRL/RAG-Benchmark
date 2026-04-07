from pydantic import BaseModel, Field


class ChunkerConfigSchema(BaseModel):
    strategy: str = Field(default="")
    chunk_size: int = Field(default=1000)
    overlap_size: int = Field(default=0)
