from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
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
from src.infrastructure.database.enums import (
    EVIDENCE_LINK_STATUS,
    RELEVANCE_GRADE,
    EvidenceLinkStatus,
    RelevanceGrade,
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
    """A question, immutable once frozen and shared by every configuration it is evaluated on.

    A frozen question is never edited: it is replaced by a new one, and
    `replaced_by_question_id` points to its successor. A replaced question leaves the
    current set (listing, freeze, import) but stays referenced by the snapshots that hold
    it. Deleting the successor clears the pointer, which undoes the replacement.
    """

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
    replaced_by_question_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("questions.id", ondelete="SET NULL"),
        index=True,
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


class EvidenceLink(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Which chunks hold the answer to a question, under one chunking configuration.

    Anchored to the configuration and not to a corpus snapshot: chunk identity depends
    only on the document and on parsing and chunking, so a confirmed link stays valid when
    the corpus grows or the embedder changes. A missing link means "not reviewed yet",
    which is different from `not_found`, a checked outcome.
    """

    __tablename__ = "evidence_links"
    __table_args__ = (UniqueConstraint("question_id", "chunking_configuration_id"),)

    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunking_configuration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chunking_configurations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[EvidenceLinkStatus] = mapped_column(
        EVIDENCE_LINK_STATUS,
        nullable=False,
        server_default=EvidenceLinkStatus.TO_REVIEW.value,
        default=EvidenceLinkStatus.TO_REVIEW,
    )
    confirmed_by: Mapped[str | None] = mapped_column(Text)
    confirmed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class EvidenceLinkChunk(UUIDPrimaryKeyMixin, Base):
    """A chunk of an evidence link, with its relevance grade."""

    __tablename__ = "evidence_link_chunks"
    __table_args__ = (UniqueConstraint("evidence_link_id", "chunk_id"),)

    evidence_link_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evidence_links.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Restrict and not cascade: chunks are immutable artefacts, and one that a person
    # confirmed as evidence must not disappear with a re-materialisation.
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chunks.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    relevance: Mapped[RelevanceGrade] = mapped_column(RELEVANCE_GRADE, nullable=False)
    graded_relevance: Mapped[int | None] = mapped_column(SmallInteger)
