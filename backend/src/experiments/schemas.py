from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.infrastructure.database.enums import (
    ArtifactStatus,
    ExecutionStatus,
    ExperimentType,
    RetrievalScope,
)


class VariantCreate(BaseModel):
    """A variant: an index build searched under a retrieval profile."""

    name: str = Field(min_length=1, max_length=200)
    index_build_id: uuid.UUID
    retrieval_profile_id: uuid.UUID
    is_baseline: bool = False


class ExperimentCreate(BaseModel):
    """Payload creating an experiment."""

    name: str = Field(min_length=1, max_length=200)
    type: ExperimentType = ExperimentType.RETRIEVAL
    corpus_snapshot_id: uuid.UUID
    qa_set_snapshot_id: uuid.UUID
    repetitions: int = Field(default=1, ge=1, le=50)
    variants: list[VariantCreate] = Field(min_length=1)
    uncovered_policy: Literal["exclude"] | None = Field(
        default=None,
        description=(
            "Required when some questions have gold documents outside the corpus snapshot: "
            "`exclude` runs them but leaves them out of the metrics' denominator."
        ),
    )


class VariantRead(BaseModel):
    """A variant with the index build and retrieval profile it points at."""

    id: uuid.UUID
    name: str
    is_baseline: bool
    index_build_id: uuid.UUID
    index_build_name: str
    index_build_status: ArtifactStatus
    retrieval_profile_id: uuid.UUID
    retrieval_profile_name: str
    top_k: int


class ExperimentRead(BaseModel):
    """An experiment as listed."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    type: ExperimentType
    corpus_snapshot_id: uuid.UUID
    qa_set_snapshot_id: uuid.UUID
    repetitions: int
    retrieval_scope: RetrievalScope
    uncovered_policy: str | None = None
    variant_count: int = 0
    created_at: dt.datetime
    # Where the two snapshots come from, so experiments can be told apart and grouped by
    # the corpus and the QA set they compare on.
    corpus_id: uuid.UUID | None = None
    corpus_name: str | None = None
    corpus_snapshot_label: str | None = None
    qa_set_id: uuid.UUID | None = None
    qa_set_name: str | None = None
    qa_set_snapshot_label: str | None = None


class UncoveredDocumentRead(BaseModel):
    document_id: uuid.UUID
    filename: str


class UncoveredQuestionRead(BaseModel):
    """A question with gold documents missing from the corpus snapshot."""

    question_id: uuid.UUID
    text: str
    missing_documents: list[UncoveredDocumentRead]


class CoverageRead(BaseModel):
    """How much of a QA snapshot a corpus snapshot can answer."""

    question_count: int
    uncovered_count: int
    uncovered: list[UncoveredQuestionRead]


class ProgressRead(BaseModel):
    """Execution counters of a run: pending includes the ones still running."""

    total: int = 0
    succeeded: int = 0
    failed: int = 0
    pending: int = 0


class RunRead(BaseModel):
    """A run with its denormalised progress, as polled by the UI."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    experiment_id: uuid.UUID
    status: ExecutionStatus
    workflow_id: str | None = None
    progress: ProgressRead
    error: str | None = None
    started_at: dt.datetime | None = None
    finished_at: dt.datetime | None = None
    created_at: dt.datetime


class RunDetail(RunRead):
    """A run with the full configuration copied at launch."""

    config_snapshot: dict[str, Any]


class RunAccepted(RunRead):
    """A launched run, stating whether this request is what started its workflow."""

    started: bool
    detail: str | None = None


class RunLaunchRequest(BaseModel):
    """Optional parameters of a run launch."""

    concurrency: int | None = Field(
        default=None,
        ge=1,
        le=50,
        description="Queries processed at once; lower it when the embedder rate limits.",
    )


class ExperimentDetail(ExperimentRead):
    """An experiment with its variants, runs and gold coverage."""

    variants: list[VariantRead]
    runs: list[RunRead]
    coverage: CoverageRead


# -- results ----------------------------------------------------------------------------


class SnapshotDeclaredRead(BaseModel):
    """The snapshot a result was computed on: a metric is meaningless without it."""

    id: uuid.UUID
    label: str
    document_count: int | None = None
    question_count: int | None = None
    corpus_id: uuid.UUID | None = None


class MetricResultRead(BaseModel):
    """Statistics of one metric for one variant, always with how many scores they rest on."""

    key: str
    direction: str
    mean: float | None
    stddev: float | None
    median: float | None
    p95: float | None
    n_effective: int
    n_excluded: int


class VariantResultRead(BaseModel):
    variant_id: uuid.UUID
    name: str
    is_baseline: bool
    index_build_id: uuid.UUID
    retrieval_profile_id: uuid.UUID
    top_k: int
    metrics: list[MetricResultRead]


class RunResultsRead(BaseModel):
    """The aggregated metrics of a run, per variant, with the snapshots they were measured on."""

    run_id: uuid.UUID
    experiment_id: uuid.UUID
    status: ExecutionStatus
    repetitions: int
    question_count: int
    corpus_snapshot: SnapshotDeclaredRead
    qa_set_snapshot: SnapshotDeclaredRead
    slice_key: str
    slice_value: str
    variants: list[VariantResultRead]


class QuestionVariantOutcomeRead(BaseModel):
    """How one variant did on a question, on its first repetition."""

    variant_id: uuid.UUID
    status: ExecutionStatus
    first_relevant_rank: float | None = None
    excluded_reason: str | None = None


class RunQuestionRead(BaseModel):
    """A question of the run with the outcome of each variant."""

    question_id: uuid.UUID
    text: str
    tags: list[str]
    answerable: bool
    outcomes: list[QuestionVariantOutcomeRead]


class HitDetailRead(BaseModel):
    """A retrieved chunk with the document it comes from and whether it counted as relevant."""

    rank: int
    score: float | None
    chunk_id: uuid.UUID | None
    document_id: uuid.UUID | None
    filename: str | None
    ordinal: int | None
    page: int | None
    text: str | None
    relevant_document: bool | None


class ExecutionDetailRead(BaseModel):
    execution_id: uuid.UUID
    repetition: int
    status: ExecutionStatus
    error: str | None = None
    excluded_reason: str | None = None
    timings: dict[str, Any] | None = None
    hits: list[HitDetailRead]


class VariantDrilldownRead(BaseModel):
    variant_id: uuid.UUID
    name: str
    is_baseline: bool
    executions: list[ExecutionDetailRead]


class QuestionDrilldownRead(BaseModel):
    """What each variant returned for one question, side by side."""

    run_id: uuid.UUID
    question_id: uuid.UUID
    text: str
    tags: list[str]
    answerable: bool
    gold_documents: list[UncoveredDocumentRead]
    variants: list[VariantDrilldownRead]
