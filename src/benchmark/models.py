import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.base import Base


class BenchmarkORM(Base):
    __tablename__ = "benchmarks"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    documents: Mapped[list["DocumentORM"]] = relationship(
        back_populates="benchmark", cascade="all, delete-orphan"
    )  # noqa: F821  # type: ignore[name-defined]
    questions: Mapped[list["QuestionORM"]] = relationship(
        back_populates="benchmark", cascade="all, delete-orphan"
    )  # noqa: F821  # type: ignore[name-defined]


class DocumentORM(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    path: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    blob_url: Mapped[str | None] = mapped_column(String, nullable=True, default=None)

    benchmark_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("benchmarks.id", ondelete="CASCADE"),
        nullable=False,
    )

    benchmark: Mapped["BenchmarkORM"] = relationship(back_populates="documents")  # noqa: F821  # type: ignore[name-defined]
    questions: Mapped[list["QuestionORM"]] = relationship(  # noqa: F821  # type: ignore[name-defined]s
        back_populates="document", cascade="all, delete-orphan"
    )  # noqa: F821  # type: ignore[name-defined]
    scans: Mapped[list["ScanORM"]] = relationship(  # noqa: F821  # type: ignore[name-defined]
        back_populates="document", cascade="all, delete-orphan"
    )  # noqa: F821  # type: ignore[name-defined]


class QuestionORM(Base):
    __tablename__ = "questions"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    query: Mapped[str] = mapped_column(String, nullable=False)
    answer: Mapped[str] = mapped_column(String, nullable=False)

    document_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    benchmark_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("benchmarks.id", ondelete="CASCADE"),
        nullable=False,
    )

    document: Mapped["DocumentORM"] = relationship(back_populates="questions")  # noqa: F821  # type: ignore[name-defined]
    benchmark: Mapped["BenchmarkORM"] = relationship(back_populates="questions")  # noqa: F821  # type: ignore[name-defined]


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
    document: Mapped["DocumentORM"] = relationship(back_populates="scans")  # noqa: F821  # type: ignore[name-defined]
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
    chunker: Mapped["ChunkerConfigORM"] = relationship(back_populates="chunks")  # noqa: F821  # type: ignore[name-defined]
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
    embedder: Mapped["EmbeddingConfigORM"] = relationship(back_populates="embeddings")  # noqa: F821  # type: ignore[name-defined]
