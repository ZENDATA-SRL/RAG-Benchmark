"""
Database ORM model for vector DB configs.

Note: this file intentionally defines the SQLAlchemy ORM model. The Pydantic models
live in `schemas.py`.
"""

import uuid

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.base import Base


class VectorDBConfigORM(Base):
    __tablename__ = "vectordb_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    backend: Mapped[str] = mapped_column(String, nullable=False, default="chromadb")
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    rag_configs: Mapped[list["RAGConfigORM"]] = relationship(back_populates="vectordb")  # noqa: F821  # type: ignore[name-defined]
