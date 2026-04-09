import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.models import AnswerORM
from src.infrastructure.database.base import Base


class DatasetORM(Base):
    __tablename__ = "datasets"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    documents: Mapped[list["DocumentORM"]] = relationship(  # noqa: F821  # type: ignore[name-defined]
        back_populates="dataset", cascade="all, delete-orphan"
    )
    questions: Mapped[list["QuestionORM"]] = relationship(  # noqa: F821  # type: ignore[name-defined]
        back_populates="dataset", cascade="all, delete-orphan"
    )
    experiments: Mapped[list["ExperimentORM"]] = relationship(  # noqa: F821  # type: ignore[name-defined]
        back_populates="dataset", cascade="all, delete-orphan"
    )


class DocumentORM(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    blob_url: Mapped[str | None] = mapped_column(String, nullable=True, default=None)

    dataset_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
    )

    dataset: Mapped["DatasetORM"] = relationship(back_populates="documents")  # noqa: F821  # type: ignore[name-defined]
    questions: Mapped[list["QuestionORM"]] = relationship(  # noqa: F821  # type: ignore[name-defined]
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
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
    )

    document: Mapped["DocumentORM"] = relationship(back_populates="questions")  # noqa: F821  # type: ignore[name-defined]
    dataset: Mapped["DatasetORM"] = relationship(back_populates="questions")  # noqa: F821  # type: ignore[name-defined]
    answers: Mapped[list["AnswerORM"]] = relationship(  # noqa: F821  # type: ignore[name-defined]
        back_populates="question", cascade="all, delete-orphan"
    )
    evaluations: Mapped[list["EvaluationORM"]] = relationship(  # noqa: F821  # type: ignore[name-defined]
        back_populates="question", cascade="all, delete-orphan"
    )


# Scan / chunk / embedding live in `src.core.models`.
# Re-exported here for backwards compatibility and to ensure they are registered
# on the shared SQLAlchemy `Base` metadata when `src.dataset.models` is imported.
from src.core.models import ScanORM  # noqa: E402

# Ensure eval models are registered on the shared SQLAlchemy `Base` registry
# when `src.dataset.models` is imported directly.
from src.evals.models import EvaluationORM  # noqa: E402,F401
