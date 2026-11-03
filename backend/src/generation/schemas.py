from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.generation.constants import DEFAULT_TEMPERATURE, MAX_MAX_STEPS
from src.infrastructure.database.enums import (
    ExecutionStatus,
    GeneratedKind,
    GenerationPhase,
    GenerationStatus,
    ProposalStatus,
    RelevanceGrade,
)

Provider = Literal["openai", "bedrock"]


class GenerationCreate(BaseModel):
    """A job generating questions from the documents of a QA set's origin corpus."""

    qa_set_id: uuid.UUID
    chunking_configuration_id: uuid.UUID
    per_document: int = Field(
        default=3,
        ge=0,
        le=50,
        description="Questions for each document, answered by chunks of that document.",
    )
    cross_document: int = Field(
        default=0,
        ge=0,
        le=200,
        description="Questions whose answer needs chunks of two or three documents.",
    )
    document_ids: list[uuid.UUID] | None = Field(
        default=None,
        description=(
            "Only these documents of the corpus are read; all of them when absent."
        ),
    )
    excluded_document_ids: list[uuid.UUID] = Field(
        default_factory=list, description="Documents of the corpus to leave out."
    )
    exclude_unmaterialized: bool = Field(
        default=False,
        description=(
            "Leave out the documents without chunks or text in the configuration, "
            "instead of refusing the job."
        ),
    )
    provider: Provider
    model: str = Field(min_length=1)
    region: str | None = Field(default=None, description="Bedrock only.")
    temperature: float = Field(default=DEFAULT_TEMPERATURE, ge=0, le=2)
    language: str | None = Field(
        default=None, description="Language of the questions; the documents' if absent."
    )
    instructions: str | None = Field(
        default=None,
        description="Free instruction for the generator, e.g. the kind of user asking.",
    )
    max_steps: int | None = Field(
        default=None, ge=5, le=MAX_MAX_STEPS, description="Model calls per unit."
    )
    concurrency: int | None = Field(default=None, ge=1, le=10)


class EstimateRead(BaseModel):
    """What a job will cost at most, before it is launched."""

    documents: int
    document_units: int
    cross_units: int
    max_steps: int
    max_model_calls: int = Field(description="Units times the steps of each, at most.")
    target_questions: int


class UnmaterializedDocumentRead(BaseModel):
    document_id: uuid.UUID
    filename: str


class CorpusDocumentRead(BaseModel):
    """A document of the set's corpus and whether a job would read it."""

    document_id: uuid.UUID
    filename: str
    materialised: bool = Field(description="Ready chunks and parsed text here.")
    excluded: bool = Field(
        description="Left out by the caller, or not among the documents chosen."
    )


class EstimateResult(BaseModel):
    """The estimate of a job, with the documents of the corpus and those it leaves out."""

    estimate: EstimateRead
    excluded: list[UnmaterializedDocumentRead]
    documents: list[CorpusDocumentRead]


class PhaseProgressRead(BaseModel):
    units: int
    succeeded: int
    failed: int
    running: int
    target: int
    produced: int


class ProposalCountsRead(BaseModel):
    pending: int
    accepted: int
    rejected: int
    by_kind: dict[str, int]


class GenerationProgressRead(BaseModel):
    document: PhaseProgressRead
    cross: PhaseProgressRead
    discards: dict[str, int] = Field(description="Submissions refused, by reason.")
    proposals: ProposalCountsRead
    documents_covered: int = Field(
        description="Documents cited by at least one proposal not rejected."
    )
    combinations: int = Field(
        description="Distinct sets of documents of the cross ones."
    )


class GenerationRead(BaseModel):
    """A job with its parameters and its live progress."""

    id: uuid.UUID
    qa_set_id: uuid.UUID
    chunking_configuration_id: uuid.UUID
    document_ids: list[uuid.UUID]
    status: GenerationStatus
    params: dict[str, Any]
    prompt_version: str
    progress: GenerationProgressRead
    estimate: EstimateRead
    error: str | None
    created_at: dt.datetime


class GenerationCreated(GenerationRead):
    """A created job, with the documents it left out."""

    excluded: list[UnmaterializedDocumentRead]


class UnitRead(BaseModel):
    """A run of the agent within a job."""

    id: uuid.UUID
    phase: GenerationPhase
    position: int
    document_id: uuid.UUID | None
    filename: str | None
    target: int
    produced: int
    status: ExecutionStatus
    end_reason: str | None
    error: str | None
    summary: str | None
    topics: list[str]
    discards: dict[str, int]
    trace_url: str | None


class ProposalChunkRead(BaseModel):
    """A chunk a proposal cites, with the quote the agent gave for it."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    ordinal: int
    page: int | None
    text: str
    quote: str
    relevance: RelevanceGrade
    rank: int


class ProposalRead(BaseModel):
    """A generated question as listed in the review queue."""

    id: uuid.UUID
    generation_job_id: uuid.UUID
    kind: GeneratedKind
    text: str
    answer: str
    status: ProposalStatus
    accepted_question_id: uuid.UUID | None
    reviewed_by: str | None
    reviewed_at: dt.datetime | None
    created_at: dt.datetime
    chunks: list[ProposalChunkRead]


class ProposalReviewRead(ProposalRead):
    """A generated question opened for review."""

    qa_set_id: uuid.UUID
    chunking_configuration_id: uuid.UUID
    phase: GenerationPhase
    trace_url: str | None
    next_proposal_id: uuid.UUID | None = Field(
        description="The next proposal waiting for a decision, for a review in sequence."
    )


class AcceptedChunk(BaseModel):
    chunk_id: uuid.UUID
    relevance: RelevanceGrade


class ProposalAccept(BaseModel):
    """The question as the reviewer accepts it, corrected or as proposed."""

    text: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    chunks: list[AcceptedChunk] = Field(min_length=1)
    annotator: str = Field(min_length=1)


class ProposalReject(BaseModel):
    annotator: str | None = None


class ProposalDecision(BaseModel):
    """The outcome of a decision, with the next proposal to review."""

    proposal: ProposalRead
    question_id: uuid.UUID | None
    next_proposal_id: uuid.UUID | None
