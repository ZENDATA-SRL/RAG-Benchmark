from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    Double,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.base import (
    Base,
    CreatedAtMixin,
    UUIDPrimaryKeyMixin,
)
from src.infrastructure.database.enums import (
    CONFIDENCE_BAND,
    EXECUTION_STATUS,
    RELEVANCE_GRADE,
    TRANSFER_STATUS,
    ConfidenceBand,
    ExecutionStatus,
    RelevanceGrade,
    TransferStatus,
)


def _uuid_fk(target: str, *, ondelete: str, nullable: bool = False, index: bool = True):
    return mapped_column(
        UUID(as_uuid=True),
        ForeignKey(target, ondelete=ondelete),
        nullable=nullable,
        index=index,
    )


class TransferJob(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Proposes the evidence chunks of a QA set's questions in a chunking configuration.

    With a source configuration it is a transfer: the chunks confirmed there are looked for
    among the chunks of the target. Without one it is the proposal for imported questions,
    which come with gold documents but no chunks: the question and its expected answer are
    what the chunks are compared with. Either way it only proposes; nothing becomes
    evidence until a person confirms it.
    """

    __tablename__ = "transfer_jobs"

    qa_set_id: Mapped[uuid.UUID] = _uuid_fk("qa_sets.id", ondelete="CASCADE")
    source_configuration_id: Mapped[uuid.UUID | None] = _uuid_fk(
        "chunking_configurations.id", ondelete="RESTRICT", nullable=True
    )
    target_configuration_id: Mapped[uuid.UUID] = _uuid_fk(
        "chunking_configurations.id", ondelete="RESTRICT"
    )
    # The embedder of the semantic signal. A chunking configuration has none of its own,
    # so the job names one; without it the ranking rests on the other signals.
    embedding_profile_id: Mapped[uuid.UUID | None] = _uuid_fk(
        "embedding_profiles.id", ondelete="RESTRICT", nullable=True
    )
    workflow_id: Mapped[str | None] = mapped_column(Text, unique=True)
    status: Mapped[TransferStatus] = mapped_column(
        TRANSFER_STATUS,
        nullable=False,
        server_default=TransferStatus.PENDING.value,
        default=TransferStatus.PENDING,
    )
    signal_weights: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict
    )
    confidence_thresholds: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict
    )
    progress: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict
    )
    recall_ceiling: Mapped[float | None] = mapped_column(Double)
    error: Mapped[str | None] = mapped_column(Text)


class TransferQuestion(UUIDPrimaryKeyMixin, Base):
    """A question a job ranks candidates for: the unit of idempotency and resume.

    A question whose candidates were written is `succeeded` and never ranked again by a
    relaunched job, even when it has no candidate at all.
    """

    __tablename__ = "transfer_questions"
    __table_args__ = (UniqueConstraint("transfer_job_id", "question_id"),)

    transfer_job_id: Mapped[uuid.UUID] = _uuid_fk(
        "transfer_jobs.id", ondelete="CASCADE", index=False
    )
    question_id: Mapped[uuid.UUID] = _uuid_fk("questions.id", ondelete="CASCADE")
    status: Mapped[ExecutionStatus] = mapped_column(
        EXECUTION_STATUS,
        nullable=False,
        server_default=ExecutionStatus.PENDING.value,
        default=ExecutionStatus.PENDING,
    )
    candidate_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0
    )
    error: Mapped[str | None] = mapped_column(Text)


class TransferCandidate(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A chunk of the target configuration proposed for a question, with its scores.

    A proposal only: confirming it is a write of the question's evidence, by a person.
    """

    __tablename__ = "transfer_candidates"
    __table_args__ = (
        UniqueConstraint("transfer_job_id", "question_id", "chunk_id"),
        Index(
            "ix_transfer_candidates_job_question_rank",
            "transfer_job_id",
            "question_id",
            "rank",
        ),
    )

    transfer_job_id: Mapped[uuid.UUID] = _uuid_fk(
        "transfer_jobs.id", ondelete="CASCADE", index=False
    )
    question_id: Mapped[uuid.UUID] = _uuid_fk(
        "questions.id", ondelete="CASCADE", index=False
    )
    # Restrict, like evidence chunks: chunks are immutable and outlive re-materialisations.
    chunk_id: Mapped[uuid.UUID] = _uuid_fk("chunks.id", ondelete="RESTRICT")
    combined_score: Mapped[float] = mapped_column(Double, nullable=False)
    semantic_score: Mapped[float | None] = mapped_column(Double)
    lexical_score: Mapped[float | None] = mapped_column(Double)
    positional_score: Mapped[float | None] = mapped_column(Double)
    confidence: Mapped[ConfidenceBand] = mapped_column(CONFIDENCE_BAND, nullable=False)
    preselected: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    # With a source, the grade of the confirmed chunk this one matches best, so a
    # pre-selected chunk keeps the grade the annotator gave in the source.
    suggested_relevance: Mapped[RelevanceGrade | None] = mapped_column(RELEVANCE_GRADE)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
