import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.base import Base


class ScanORM(Base):
    __tablename__ = "scans"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ocr_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("ocr_configs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    text: Mapped[str] = mapped_column(String, nullable=False)

    ocr: Mapped["OCRConfigORM"] = relationship()  # noqa: F821  # type: ignore[name-defined]
    document: Mapped["DocumentORM"] = relationship(  # noqa: F821  # type: ignore[name-defined]
        back_populates="scans"
    )
    chunks: Mapped[list["ChunkORM"]] = relationship(  # noqa: F821  # type: ignore[name-defined]
        back_populates="scan", cascade="all, delete-orphan"
    )


class ChunkORM(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scan_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("scans.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunker_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("chunker_configs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    start_index: Mapped[int] = mapped_column(Integer, nullable=False)
    end_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(String, nullable=False)

    scan: Mapped["ScanORM"] = relationship(back_populates="chunks")  # noqa: F821  # type: ignore[name-defined]
    chunker: Mapped["ChunkerConfigORM"] = relationship(  # noqa: F821  # type: ignore[name-defined]
        back_populates="chunks"
    )
    embeddings: Mapped[list["EmbeddingORM"]] = relationship(  # noqa: F821  # type: ignore[name-defined]
        back_populates="chunk", cascade="all, delete-orphan"
    )


class EmbeddingORM(Base):
    __tablename__ = "embeddings"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("chunks.id", ondelete="CASCADE"),
        nullable=False,
    )
    embedder_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("embedding_configs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    text: Mapped[str] = mapped_column(String, nullable=False)
    vectors: Mapped[list[float]] = mapped_column(ARRAY(Float), nullable=False)

    chunk: Mapped["ChunkORM"] = relationship(back_populates="embeddings")  # noqa: F821  # type: ignore[name-defined]
    embedder: Mapped["EmbeddingConfigORM"] = relationship(  # noqa: F821  # type: ignore[name-defined]
        back_populates="embeddings"
    )


class ExperimentORM(Base):
    __tablename__ = "experiments"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    dataset: Mapped["DatasetORM"] = relationship(back_populates="experiments")  # noqa: F821  # type: ignore[name-defined]
    answers: Mapped[list["AnswerORM"]] = relationship(  # noqa: F821  # type: ignore[name-defined]
        back_populates="experiment", cascade="all, delete-orphan"
    )


class AnswerORM(Base):
    __tablename__ = "answers"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    experiment_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("experiments.id", ondelete="CASCADE"),
        nullable=False,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
    )
    answer: Mapped[str] = mapped_column(String, nullable=False)

    experiment: Mapped["ExperimentORM"] = relationship(back_populates="answers")  # noqa: F821  # type: ignore[name-defined]
    question: Mapped["QuestionORM"] = relationship(back_populates="answers")  # noqa: F821  # type: ignore[name-defined]
    evaluations: Mapped[list["EvaluationORM"]] = relationship(  # noqa: F821  # type: ignore[name-defined]
        back_populates="answer", cascade="all, delete-orphan"
    )


# Ensure eval models are registered on the same SQLAlchemy `Base` registry
# when `src.core.models` is imported directly (prevents relationship resolution
# errors like "failed to locate a name ('EvaluationORM')").
from src.evals.models import EvaluationORM  # noqa: E402,F401
