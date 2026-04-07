from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# Remember to implement the resolution
class SolverConfig(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    top_k: int = Field(default=10)
    reranking: Literal["llm", "semantic"] = Field(default=False) #should it be configurable or should I just use the default?
    hybrid: bool = Field(default=False)
    strategy: str = Field(default="")

class RetrievalConfig(BaseModel):
    id: UUID = Field(default_factory=uuid4)