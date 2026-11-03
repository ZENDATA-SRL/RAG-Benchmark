from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.base import (
    Base,
    CreatedAtMixin,
    UUIDPrimaryKeyMixin,
)
from src.infrastructure.database.enums import (
    EXECUTION_STATUS,
    GENERATED_KIND,
    GENERATION_PHASE,
    GENERATION_STATUS,
    PROPOSAL_STATUS,
    RELEVANCE_GRADE,
    ExecutionStatus,
    GeneratedKind,
    GenerationPhase,
    GenerationStatus,
    ProposalStatus,
    RelevanceGrade,
)


def _uuid_fk(target: str, *, ondelete: str, nullable: bool = False, index: bool = True):
    return mapped_column(
        UUID(as_uuid=True),
        ForeignKey(target, ondelete=ondelete),
        nullable=nullable,
        index=index,
    )


class GenerationJob(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Asks an agent to write questions from the documents of a QA set's corpus.

    The agent reads the chunks of one chunking configuration and proposes questions with
    their expected answer and the chunks that hold it. It only proposes: a question enters
    the set, with confirmed evidence, when a person accepts it.

    The generator's parameters live on the job rather than in a content-addressed profile:
    a job is launched to fill a set, not compared with another generator.
    """

    __tablename__ = "generation_jobs"

    qa_set_id: Mapped[uuid.UUID] = _uuid_fk("qa_sets.id", ondelete="CASCADE")
    chunking_configuration_id: Mapped[uuid.UUID] = _uuid_fk(
        "chunking_configurations.id", ondelete="RESTRICT"
    )
    # The documents the job reads, in the order their short references are numbered.
    document_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False
    )
    params: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict
    )
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[GenerationStatus] = mapped_column(
        GENERATION_STATUS,
        nullable=False,
        server_default=GenerationStatus.PENDING.value,
        default=GenerationStatus.PENDING,
    )
    progress: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict
    )
    workflow_id: Mapped[str | None] = mapped_column(Text, unique=True)
    error: Mapped[str | None] = mapped_column(Text)


class GenerationUnit(UUIDPrimaryKeyMixin, Base):
    """One run of the agent with a target number of questions: the unit of resume.

    A unit of the document phase reads one document; a unit of the cross phase reads all
    of them, and the cross units run one after the other so each sees what the previous
    ones delivered. Every question is saved as soon as it passes the checks, so an
    interrupted unit restarts with what is left of its target.
    """

    __tablename__ = "generation_units"
    __table_args__ = (
        Index(
            "ix_generation_units_job_phase_status_position",
            "generation_job_id",
            "phase",
            "status",
            "position",
        ),
    )

    generation_job_id: Mapped[uuid.UUID] = _uuid_fk(
        "generation_jobs.id", ondelete="CASCADE", index=False
    )
    phase: Mapped[GenerationPhase] = mapped_column(GENERATION_PHASE, nullable=False)
    document_id: Mapped[uuid.UUID | None] = _uuid_fk(
        "documents.id", ondelete="CASCADE", nullable=True, index=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    target: Mapped[int] = mapped_column(Integer, nullable=False)
    produced: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0
    )
    status: Mapped[ExecutionStatus] = mapped_column(
        EXECUTION_STATUS,
        nullable=False,
        server_default=ExecutionStatus.PENDING.value,
        default=ExecutionStatus.PENDING,
    )
    # What the document phase learnt of its document, shown to the cross phase so it can
    # pick documents that are actually related.
    summary: Mapped[str | None] = mapped_column(Text)
    topics: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb"), default=list
    )
    # Submissions the checks refused, by reason.
    discards: Mapped[dict[str, int]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict
    )
    end_reason: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    langfuse_trace_id: Mapped[str | None] = mapped_column(Text)


class GeneratedQuestion(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A question the agent proposed, waiting for a person to accept or reject it.

    It keeps the text the agent wrote even after a corrected version is accepted, so the
    share of corrections says something about the generator.
    """

    __tablename__ = "generated_questions"
    __table_args__ = (
        Index(
            "ix_generated_questions_job_status",
            "generation_job_id",
            "status",
        ),
    )

    generation_job_id: Mapped[uuid.UUID] = _uuid_fk(
        "generation_jobs.id", ondelete="CASCADE", index=False
    )
    unit_id: Mapped[uuid.UUID] = _uuid_fk("generation_units.id", ondelete="CASCADE")
    kind: Mapped[GeneratedKind] = mapped_column(GENERATED_KIND, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ProposalStatus] = mapped_column(
        PROPOSAL_STATUS,
        nullable=False,
        server_default=ProposalStatus.PENDING.value,
        default=ProposalStatus.PENDING,
    )
    accepted_question_id: Mapped[uuid.UUID | None] = _uuid_fk(
        "questions.id", ondelete="SET NULL", nullable=True
    )
    reviewed_by: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class GeneratedQuestionChunk(Base):
    """A chunk a generated question cites, with the passage quoted from it.

    The grade is the platform's, from the shape of the evidence: a lone chunk answers on
    its own, several chunks only together. The quote serves the checks and the review;
    the gold is the set of chunks.
    """

    __tablename__ = "generated_question_chunks"

    generated_question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("generated_questions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # Restrict, like evidence chunks: chunks are immutable and outlive re-materialisations.
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chunks.id", ondelete="RESTRICT"),
        primary_key=True,
        index=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    relevance: Mapped[RelevanceGrade] = mapped_column(RELEVANCE_GRADE, nullable=False)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
