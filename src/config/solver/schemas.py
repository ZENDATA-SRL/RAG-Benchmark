from pydantic import BaseModel, Field


class SolverConfigSchema(BaseModel):
    strategy: str = Field(default="")
