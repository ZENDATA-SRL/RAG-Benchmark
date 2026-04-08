import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.database.base import Base


class BenchmarkORM(Base):
    __tablename__ = "benchmarks"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    documents: Mapped[list["DocumentORM"]] = relationship(back_populates="benchmark", cascade="all, delete-orphan")
    questions: Mapped[list["QuestionORM"]] = relationship(back_populates="benchmark", cascade="all, delete-orphan")


class DocumentORM(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    path: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    blob_url: Mapped[str | None] = mapped_column(String, nullable=True, default=None)

    benchmark_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("benchmarks.id", ondelete="CASCADE"), nullable=False
    )

    benchmark: Mapped["BenchmarkORM"] = relationship(back_populates="documents")
    questions: Mapped[list["QuestionORM"]] = relationship(back_populates="document", cascade="all, delete-orphan")
    scans: Mapped[list["ScanORM"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class QuestionORM(Base):
    __tablename__ = "questions"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    query: Mapped[str] = mapped_column(String, nullable=False)
    answer: Mapped[str] = mapped_column(String, nullable=False)

    document_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    benchmark_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("benchmarks.id", ondelete="CASCADE"), nullable=False
    )

    document: Mapped["DocumentORM"] = relationship(back_populates="questions")
    benchmark: Mapped["BenchmarkORM"] = relationship(back_populates="questions")
