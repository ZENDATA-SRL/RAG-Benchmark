from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.base import (
    Base,
    CreatedAtMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class QASet(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A set of questions, reusable on any corpus snapshot that holds its gold documents.

    The origin corpus is only where the questions were written and where gold file names
    are resolved: it is not a constraint, because tying a set to one snapshot would make it
    unusable as soon as the corpus grows. The constraint that matters is checked when an
    experiment is created.
    """

    __tablename__ = "qa_sets"

    origin_corpus_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("corpora.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class QASetSnapshot(UUIDPrimaryKeyMixin, Base):
    """Immutable freeze of the questions of a set, taken before an experiment runs.

    Deduplicated by composition: `composition_hash` is the sha-256 over the sorted question
    ids, so freezing the same questions twice returns the same snapshot.
    """

    __tablename__ = "qa_set_snapshots"
    __table_args__ = (UniqueConstraint("qa_set_id", "composition_hash"),)

    qa_set_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("qa_sets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    question_count: Mapped[int] = mapped_column(Integer, nullable=False)
    composition_hash: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    langfuse_dataset_id: Mapped[str | None] = mapped_column(Text)
    frozen_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Question(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A question, immutable and shared by every configuration it is evaluated on."""

    __tablename__ = "questions"
    __table_args__ = (Index("ix_questions_tags", "tags", postgresql_using="gin"),)

    qa_set_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("qa_sets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    attachments: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default="[]", default=list
    )
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=sql_text("'{}'"), default=list
    )
    answerable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sql_text("true"), default=True
    )


class QASnapshotQuestion(Base):
    """Composition of a snapshot: questions are referenced, never copied."""

    __tablename__ = "qa_snapshot_questions"

    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("qa_set_snapshots.id", ondelete="CASCADE"),
        primary_key=True,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("questions.id", ondelete="RESTRICT"),
        primary_key=True,
    )


class GoldDocument(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A document that contains the answer to a question.

    A list and not a single document: a paragraph repeated in three attachments has three
    valid gold documents, and any of them counts.
    """

    __tablename__ = "gold_documents"
    __table_args__ = (UniqueConstraint("question_id", "document_id"),)

    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )


class ExpectedAnswer(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """An acceptable answer to a question, with an optional rubric for the judge.

    Several answers can be acceptable for one question; `is_primary` marks the one shown
    first and handed to the judge as the reference.
    """

    __tablename__ = "expected_answers"

    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    rubric: Mapped[dict | None] = mapped_column(JSONB)
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sql_text("false"), default=False
    )
