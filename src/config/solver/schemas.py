from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SolverConfigSchema(BaseModel):
    top_k: int = Field(default=10)
    reranking: Literal["llm", "semantic"] | None = Field(
        default=None
    )  # should it be configurable or should I just use the default?
    hyde: bool = Field(default=False)
    hybrid: bool = Field(default=False)
    strategy: str = Field(default="")


class SolverConfig(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    top_k: int
    reranking: Literal["llm", "semantic"]
    hyde: bool
    hybrid: bool
    strategy: str
