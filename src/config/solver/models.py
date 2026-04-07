from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class SolverConfig(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    strategy: str = Field(default="")
