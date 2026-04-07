from typing import Literal
from pydantic import BaseModel, Field


class SolverConfigSchema(BaseModel):
    top_k: int = Field(default=10)
    reranking: Literal["llm", "semantic"] | None= Field(default=None) #should it be configurable or should I just use the default?
    hybrid: bool = Field(default=False)
    strategy: str = Field(default="")
