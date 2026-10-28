from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, Field

from src.infrastructure.database.enums import (
    ConfidenceBand,
    RelevanceGrade,
    TransferStatus,
)

QueueState = Literal[
    "preselected", "to_review", "no_candidates", "pending", "failed", "decided"
]


class SignalWeights(BaseModel):
    """Weights of the three signals; the defaults apply to those left out."""

    semantic: float | None = Field(default=None, ge=0, le=1)
    lexical: float | None = Field(default=None, ge=0, le=1)
    positional: float | None = Field(default=None, ge=0, le=1)


class ConfidenceThresholds(BaseModel):
    """Bands of the combined score and the lexical score above which a chunk is ticked."""

    high: float | None = Field(default=None, ge=0, le=1)
    low: float | None = Field(default=None, ge=0, le=1)
    preselect: float | None = Field(default=None, ge=0, le=1)


class TransferCreate(BaseModel):
    """A job proposing evidence chunks of a QA set in a chunking configuration."""

    qa_set_id: uuid.UUID
    target_configuration_id: uuid.UUID
    source_configuration_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "Where the evidence is already confirmed, to transfer it; absent, the job "
            "proposes chunks for questions that only have gold documents."
        ),
    )
    embedding_profile_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "Embedder of the semantic signal; defaults to the one of the newest ready "
            "index on the target configuration, and without any the signal is skipped."
        ),
    )
    signal_weights: SignalWeights | None = None
    confidence_thresholds: ConfidenceThresholds | None = None
    question_ids: list[uuid.UUID] | None = Field(
        default=None, description="A subset of the set's questions."
    )
    exclude_uncovered: bool = Field(
        default=False,
        description=(
            "Leave out the questions whose gold documents have no chunks in the target "
            "configuration, instead of refusing the job."
        ),
    )
    concurrency: int | None = Field(default=None, ge=1, le=20)


class TransferProgressRead(BaseModel):
    total: int
    ranked: int
    failed: int
    reviewed: int
    confirmed: int
    not_found: int


class UncoveredDocumentRead(BaseModel):
    document_id: uuid.UUID
    filename: str


class ExcludedQuestionRead(BaseModel):
    """A question left out of a job because its candidates cannot be computed."""

    question_id: uuid.UUID
    text: str
    reason: str
    missing_documents: list[UncoveredDocumentRead]


class TransferRead(BaseModel):
    """A job with its live progress and the recall ceiling of its target configuration."""

    id: uuid.UUID
    qa_set_id: uuid.UUID
    source_configuration_id: uuid.UUID | None
    target_configuration_id: uuid.UUID
    embedding_profile_id: uuid.UUID | None
    status: TransferStatus
    signal_weights: dict[str, float]
    confidence_thresholds: dict[str, float]
    progress: TransferProgressRead
    skipped: dict[str, int] = Field(
        default_factory=dict,
        description="Questions of the set not in the job, by reason.",
    )
    recall_ceiling: float | None
    error: str | None
    created_at: dt.datetime


class TransferCreated(TransferRead):
    """A created job, with the questions excluded because they cannot be ranked."""

    excluded: list[ExcludedQuestionRead]


class QueueRowRead(BaseModel):
    """A question of a job in the review queue."""

    question_id: uuid.UUID
    text: str
    state: QueueState
    evidence_status: str
    top_score: float | None
    plausible: int = Field(description="Candidates in the high or medium band.")
    preselected: int
    error: str | None = None


class CandidateRead(BaseModel):
    """A proposed chunk, its scores and band; a proposal, never evidence by itself."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    ordinal: int
    page: int | None
    text: str
    rank: int
    combined_score: float
    semantic_score: float | None
    lexical_score: float | None
    positional_score: float | None
    confidence: ConfidenceBand
    preselected: bool
    suggested_relevance: RelevanceGrade | None


class ReferenceChunkRead(BaseModel):
    """A chunk confirmed in the source configuration: what the candidates are matched to."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    ordinal: int
    page: int | None
    text: str
    relevance: RelevanceGrade


class QuestionReviewRead(BaseModel):
    """A question of a job opened for review."""

    transfer_job_id: uuid.UUID
    question_id: uuid.UUID
    qa_set_id: uuid.UUID
    text: str
    state: QueueState
    evidence_status: str
    target_configuration_id: uuid.UUID
    reference: list[ReferenceChunkRead]
    candidates: list[CandidateRead]
    next_question_id: uuid.UUID | None = Field(
        description="The next question waiting for a decision, for a review in sequence."
    )
