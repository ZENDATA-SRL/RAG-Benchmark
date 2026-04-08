import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.database.base import Base


class RAGConfigORM(Base):
    __tablename__ = "rag_configs"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    ocr_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("ocr_configs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    chunker_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("chunker_configs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    embedder_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("embedding_configs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    llm_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("llm_configs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    solver_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("solver_configs.id", ondelete="RESTRICT"),
        nullable=False,
    )

    ocr: Mapped["OCRConfigORM"] = relationship(back_populates="rag_configs")
    chunker: Mapped["ChunkerConfigORM"] = relationship(back_populates="rag_configs")
    embedder: Mapped["EmbeddingConfigORM"] = relationship(back_populates="rag_configs")
    llm: Mapped["LLMConfigORM"] = relationship(back_populates="rag_configs")
    solver: Mapped["SolverConfigORM"] = relationship(back_populates="rag_configs")
