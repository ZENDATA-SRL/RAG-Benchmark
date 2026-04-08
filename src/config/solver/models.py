import uuid
from typing import Literal

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.database.base import Base


class SolverConfigORM(Base):
    __tablename__ = "solver_configs"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    top_k: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    reranking: Mapped[str] = mapped_column(String, nullable=False, default="semantic")
    hyde: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hybrid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    strategy: Mapped[str] = mapped_column(String, nullable=False, default="")

    rag_configs: Mapped[list["RAGConfigORM"]] = relationship(back_populates="solver")

    # Keep a lightweight runtime type hint for call sites that used Literal before.
    RerankingStrategy = Literal["llm", "semantic"]