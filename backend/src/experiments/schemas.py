from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.infrastructure.database.enums import (
    ArtifactStatus,
    ExecutionStatus,
    ExperimentType,
    MetricFamily,
    MetricLevel,
    RelevanceGrade,
    RetrievalScope,
)


class VariantCreate(BaseModel):
    """An index build, a retrieval profile and, for Q&A, an answer profile."""

    index_build_id: uuid.UUID
    retrieval_profile_id: uuid.UUID
    answer_profile_id: uuid.UUID | None = Field(
        default=None, description="Required in a Q&A experiment, refused otherwise."
    )
    is_baseline: bool = False


class ExperimentCreate(BaseModel):
    """Payload creating an experiment."""

    name: str = Field(min_length=1, max_length=200)
    type: ExperimentType = ExperimentType.RETRIEVAL
    corpus_snapshot_id: uuid.UUID
    qa_set_snapshot_id: uuid.UUID
    repetitions: int = Field(default=1, ge=1, le=50)
    retrieval_scope: RetrievalScope = Field(
        default=RetrievalScope.RETRIEVED,
        description=(
            "Chunks the set metrics of a Q&A experiment are computed on: everything "
            "retrieved, or what the answer system cited. `cited` needs systems that "
            "declare citations."
        ),
    )
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
    answer_profile_id: uuid.UUID | None = None
    answer_profile_name: str | None = None


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


class EvaluationProgressRead(BaseModel):
    """The latest re-evaluation of a run: its state and how many executions it scored."""

    status: Literal["running", "succeeded", "failed"]
    evaluated: int = 0
    total: int = 0
    attempt: int = 1
    error: str | None = None


class ProgressRead(BaseModel):
    """Execution counters of a run: pending includes the ones still running."""

    total: int = 0
    succeeded: int = 0
    failed: int = 0
    pending: int = 0
    evaluation: EvaluationProgressRead | None = Field(
        default=None, description="Absent until the run is re-evaluated."
    )


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
    """Statistics of one metric for one variant, always with how many questions they rest on."""

    key: str
    family: MetricFamily
    level: MetricLevel | None = Field(
        description="Empty for the call metrics, which read no gold."
    )
    direction: str
    aggregation: str = Field(
        description="The statistic the metric is read on: `mean` or `median`."
    )
    description: str = Field(
        default="", description="What the metric measures and how it is computed."
    )
    mean: float | None
    stddev: float | None
    median: float | None
    p95: float | None
    n_effective: int
    n_excluded: int
    excluded_reasons: dict[str, int] = Field(
        default_factory=dict,
        description="Excluded questions by reason; they add up to `n_excluded`.",
    )


class VariantResultRead(BaseModel):
    variant_id: uuid.UUID
    name: str
    is_baseline: bool
    index_build_id: uuid.UUID
    retrieval_profile_id: uuid.UUID
    top_k: int
    metrics: list[MetricResultRead]


class EvidenceCountsRead(BaseModel):
    """How the evidence of the answerable questions stood when the run was scored."""

    answerable: int
    confirmed: int
    not_found: int
    to_review: int
    not_reviewed: int


class ResultGroupRead(BaseModel):
    """The variants that search one chunking configuration, whose chunk metrics compare."""

    chunking_configuration_id: uuid.UUID
    chunking_configuration_name: str
    parsing: str
    chunking: str
    evidence_coverage: EvidenceCountsRead | None = Field(
        default=None,
        description="Absent when the run was scored before chunk-level evidence existed.",
    )
    recall_ceiling: float | None = Field(
        default=None,
        description=(
            "1 - not found / reviewed: the share of the reviewed questions whose evidence "
            "exists among the chunks of this configuration."
        ),
    )
    variants: list[VariantResultRead]


class CrossGroupRead(BaseModel):
    """Which metrics compare across chunking configurations, and why only those."""

    keys: list[str]
    reason: str


class ChunkGoldRead(BaseModel):
    """The evidence the chunk metrics were computed on: when, and its fingerprint."""

    evaluated_at: dt.datetime
    hash: str


class RunResultsRead(BaseModel):
    """The aggregated metrics of a run, grouped by chunking configuration.

    Chunk-level metrics only compare within a group, since the evidence is confirmed on
    the chunks of one configuration; document-level metrics compare everywhere.
    """

    run_id: uuid.UUID
    experiment_id: uuid.UUID
    experiment_type: ExperimentType = Field(
        description=(
            "Decides the metrics: `retrieval` has the ranked ones only, `qa` also the set "
            "and call metrics."
        )
    )
    status: ExecutionStatus
    repetitions: int
    question_count: int
    corpus_snapshot: SnapshotDeclaredRead
    qa_set_snapshot: SnapshotDeclaredRead
    slice_key: str
    slice_value: str
    chunk_gold: ChunkGoldRead | None = None
    cross_group_metrics: CrossGroupRead
    groups: list[ResultGroupRead]


class QuestionVariantOutcomeRead(BaseModel):
    """How one variant did on a question, on its first repetition, at both levels."""

    variant_id: uuid.UUID
    status: ExecutionStatus
    first_relevant_rank: float | None = None
    excluded_reason: str | None = None
    chunk_first_relevant_rank: float | None = None
    chunk_excluded_reason: str | None = None
    answer_text: str | None = Field(
        default=None, description="The answer, in a Q&A run; empty in a retrieval one."
    )
    refused: bool | None = None


class RunQuestionRead(BaseModel):
    """A question of the run with the outcome of each variant."""

    question_id: uuid.UUID
    text: str
    tags: list[str]
    answerable: bool
    expected_answer: str | None = Field(
        default=None, description="The primary expected answer, when there is one."
    )
    outcomes: list[QuestionVariantOutcomeRead]


class HitOccurrenceRead(BaseModel):
    """One time a chunk was returned: by which call, at which rank."""

    call_index: int
    rank: int
    score: float | None


class CallDetailRead(BaseModel):
    """One retrieval call of an execution, and how much it brought that was new."""

    call_index: int
    query_text: str
    hit_count: int
    new_chunk_count: int = Field(
        description="Chunks this call returned that no earlier call of the execution had."
    )


class HitDetailRead(BaseModel):
    """A distinct chunk of an execution, with every time it was returned and why it counts.

    `rank` and `score` are those of its first occurrence. A chunk cited by the answer
    system and never retrieved has `retrieved = false` and no occurrence.
    """

    rank: int | None
    score: float | None
    chunk_id: uuid.UUID | None
    document_id: uuid.UUID | None
    filename: str | None
    ordinal: int | None
    page: int | None
    text: str | None
    relevant_document: bool | None
    relevant_chunk: bool | None = None
    relevance: RelevanceGrade | None = Field(
        default=None, description="Grade of the chunk when it is an evidence chunk."
    )
    occurrences: list[HitOccurrenceRead] = Field(default_factory=list)
    retrieved: bool = True
    cited: bool | None = Field(
        default=None,
        description="Empty when the answer system declares no citations.",
    )


class ExecutionDetailRead(BaseModel):
    execution_id: uuid.UUID
    repetition: int
    status: ExecutionStatus
    error: str | None = None
    excluded_reason: str | None = None
    chunk_excluded_reason: str | None = None
    timings: dict[str, Any] | None = None
    answer_text: str | None = None
    refused: bool | None = None
    usage: dict[str, Any] | None = None
    calls: list[CallDetailRead] = Field(default_factory=list)
    citations_declared: bool = False
    hits: list[HitDetailRead] = Field(
        description=(
            "Distinct chunks in order of first retrieval, then the chunks cited and never "
            "retrieved."
        )
    )


class GoldChunkRead(BaseModel):
    """An evidence chunk of the question, and whether the variant retrieved it."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    ordinal: int
    page: int | None
    text: str
    relevance: RelevanceGrade
    graded_relevance: int | None
    retrieved: bool


class VariantDrilldownRead(BaseModel):
    variant_id: uuid.UUID
    name: str
    is_baseline: bool
    chunking_configuration_id: uuid.UUID
    evidence_status: str = Field(
        description=(
            "Of the question under the variant's configuration: `not_reviewed`, "
            "`to_review`, `confirmed` or `not_found`."
        )
    )
    gold_chunks: list[GoldChunkRead]
    executions: list[ExecutionDetailRead]


class QuestionDrilldownRead(BaseModel):
    """What each variant returned for one question, side by side."""

    run_id: uuid.UUID
    question_id: uuid.UUID
    qa_set_id: uuid.UUID
    text: str
    tags: list[str]
    answerable: bool
    expected_answer: str | None = Field(
        default=None, description="The primary expected answer, when there is one."
    )
    gold_documents: list[UncoveredDocumentRead]
    variants: list[VariantDrilldownRead]
