from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
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
    EVALUATOR_KIND,
    EXECUTION_STATUS,
    EXPERIMENT_TYPE,
    METRIC_FAMILY,
    METRIC_LEVEL,
    RETRIEVAL_SCOPE,
    RETRIEVAL_STAGE,
    EvaluatorKind,
    ExecutionStatus,
    ExperimentType,
    MetricFamily,
    MetricLevel,
    RetrievalScope,
    RetrievalStage,
)


def _uuid_fk(target: str, *, ondelete: str, nullable: bool = False, index: bool = True):
    return mapped_column(
        UUID(as_uuid=True),
        ForeignKey(target, ondelete=ondelete),
        nullable=nullable,
        index=index,
    )


class Experiment(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A comparison of variants on one corpus snapshot and one frozen question set.

    The corpus snapshot is repeated here although it can be derived from the variants'
    index builds: it is the guard that makes "every variant searches the same documents"
    expressible and checkable.
    """

    __tablename__ = "experiments"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[ExperimentType] = mapped_column(EXPERIMENT_TYPE, nullable=False)
    corpus_snapshot_id: Mapped[uuid.UUID] = _uuid_fk(
        "corpus_snapshots.id", ondelete="RESTRICT"
    )
    qa_set_snapshot_id: Mapped[uuid.UUID] = _uuid_fk(
        "qa_set_snapshots.id", ondelete="RESTRICT"
    )
    repetitions: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1", default=1
    )
    retrieval_scope: Mapped[RetrievalScope] = mapped_column(
        RETRIEVAL_SCOPE,
        nullable=False,
        server_default=RetrievalScope.RETRIEVED.value,
        default=RetrievalScope.RETRIEVED,
    )
    uncovered_policy: Mapped[str | None] = mapped_column(Text)


class Variant(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Index build x retrieval profile (x answer profile) compared inside an experiment."""

    __tablename__ = "variants"

    experiment_id: Mapped[uuid.UUID] = _uuid_fk("experiments.id", ondelete="CASCADE")
    name: Mapped[str] = mapped_column(Text, nullable=False)
    index_build_id: Mapped[uuid.UUID] = _uuid_fk("index_builds.id", ondelete="RESTRICT")
    retrieval_profile_id: Mapped[uuid.UUID] = _uuid_fk(
        "retrieval_profiles.id", ondelete="RESTRICT"
    )
    answer_profile_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    is_baseline: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )


class Run(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One execution of an experiment, with the whole configuration copied by value.

    `progress` is a denormalised copy of the execution counters for the UI to poll; the
    authoritative state stays in Temporal.
    """

    __tablename__ = "runs"

    experiment_id: Mapped[uuid.UUID] = _uuid_fk("experiments.id", ondelete="CASCADE")
    workflow_id: Mapped[str | None] = mapped_column(Text, unique=True)
    status: Mapped[ExecutionStatus] = mapped_column(
        EXECUTION_STATUS,
        nullable=False,
        server_default=ExecutionStatus.PENDING.value,
        default=ExecutionStatus.PENDING,
    )
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    progress: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}", default=dict
    )
    error: Mapped[str | None] = mapped_column(Text)
    langfuse_run_name: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class Execution(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One question x variant x repetition: the unit of idempotency and resume."""

    __tablename__ = "executions"
    __table_args__ = (
        UniqueConstraint("run_id", "variant_id", "question_id", "repetition"),
        Index("ix_executions_run_id_variant_id", "run_id", "variant_id"),
    )

    run_id: Mapped[uuid.UUID] = _uuid_fk("runs.id", ondelete="CASCADE", index=False)
    variant_id: Mapped[uuid.UUID] = _uuid_fk(
        "variants.id", ondelete="RESTRICT", index=False
    )
    question_id: Mapped[uuid.UUID] = _uuid_fk(
        "questions.id", ondelete="RESTRICT", index=False
    )
    repetition: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ExecutionStatus] = mapped_column(
        EXECUTION_STATUS,
        nullable=False,
        server_default=ExecutionStatus.PENDING.value,
        default=ExecutionStatus.PENDING,
    )
    answer_text: Mapped[str | None] = mapped_column(Text)
    refused: Mapped[bool | None] = mapped_column(Boolean)
    answer_payload_uri: Mapped[str | None] = mapped_column(Text)
    usage: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    timings: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    langfuse_trace_id: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)


class RetrievalCall(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One invocation of the retrieval tool; an agentic system makes several per execution."""

    __tablename__ = "retrieval_calls"
    __table_args__ = (UniqueConstraint("execution_id", "call_index"),)

    execution_id: Mapped[uuid.UUID] = _uuid_fk(
        "executions.id", ondelete="CASCADE", index=False
    )
    call_index: Mapped[int] = mapped_column(Integer, nullable=False)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)


class RetrievalHit(UUIDPrimaryKeyMixin, Base):
    """A chunk returned by a call, with its rank, score and relevance flags."""

    __tablename__ = "retrieval_hits"
    __table_args__ = (
        Index(
            "ix_retrieval_hits_retrieval_call_id_stage_rank",
            "retrieval_call_id",
            "stage",
            "rank",
        ),
    )

    retrieval_call_id: Mapped[uuid.UUID] = _uuid_fk(
        "retrieval_calls.id", ondelete="CASCADE", index=False
    )
    chunk_id: Mapped[uuid.UUID | None] = _uuid_fk(
        "chunks.id", ondelete="SET NULL", nullable=True, index=False
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float | None] = mapped_column(Double)
    stage: Mapped[RetrievalStage] = mapped_column(RETRIEVAL_STAGE, nullable=False)
    in_context: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    cited: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    relevant_document: Mapped[bool | None] = mapped_column(Boolean)
    relevant_chunk: Mapped[bool | None] = mapped_column(Boolean)


class MetricDefinition(UUIDPrimaryKeyMixin, Base):
    """A metric the platform can compute: key, family, level, direction, aggregation."""

    __tablename__ = "metric_definitions"

    key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    family: Mapped[MetricFamily] = mapped_column(METRIC_FAMILY, nullable=False)
    level: Mapped[MetricLevel | None] = mapped_column(METRIC_LEVEL)
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    aggregation: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class Evaluator(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Who scores an execution: deterministic code, an LLM judge or a person."""

    __tablename__ = "evaluators"

    kind: Mapped[EvaluatorKind] = mapped_column(EVALUATOR_KIND, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    component_version_id: Mapped[uuid.UUID | None] = _uuid_fk(
        "component_versions.id", ondelete="RESTRICT", nullable=True
    )
    prompt: Mapped[str | None] = mapped_column(Text)
    rubric: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    version: Mapped[str] = mapped_column(Text, nullable=False)


class Evaluation(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """The score of one execution on one metric, or the reason it does not count."""

    __tablename__ = "evaluations"
    __table_args__ = (
        UniqueConstraint("execution_id", "metric_definition_id", "evaluator_id"),
    )

    execution_id: Mapped[uuid.UUID] = _uuid_fk(
        "executions.id", ondelete="CASCADE", index=False
    )
    metric_definition_id: Mapped[uuid.UUID] = _uuid_fk(
        "metric_definitions.id", ondelete="RESTRICT", index=False
    )
    evaluator_id: Mapped[uuid.UUID] = _uuid_fk(
        "evaluators.id", ondelete="RESTRICT", index=False
    )
    score: Mapped[float | None] = mapped_column(Double)
    excluded: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    exclusion_reason: Mapped[str | None] = mapped_column(Text)
    langfuse_score_id: Mapped[str | None] = mapped_column(Text)


class MetricAggregate(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Statistics of a metric for a run and a variant, with effective and excluded counts."""

    __tablename__ = "metric_aggregates"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "variant_id", "metric_definition_id", "slice_key", "slice_value"
        ),
    )

    run_id: Mapped[uuid.UUID] = _uuid_fk("runs.id", ondelete="CASCADE", index=False)
    variant_id: Mapped[uuid.UUID] = _uuid_fk(
        "variants.id", ondelete="RESTRICT", index=False
    )
    metric_definition_id: Mapped[uuid.UUID] = _uuid_fk(
        "metric_definitions.id", ondelete="RESTRICT", index=False
    )
    slice_key: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="all", default="all"
    )
    slice_value: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="all", default="all"
    )
    mean: Mapped[float | None] = mapped_column(Double)
    stddev: Mapped[float | None] = mapped_column(Double)
    median: Mapped[float | None] = mapped_column(Double)
    p95: Mapped[float | None] = mapped_column(Double)
    ci_low: Mapped[float | None] = mapped_column(Double)
    ci_high: Mapped[float | None] = mapped_column(Double)
    n_effective: Mapped[int] = mapped_column(Integer, nullable=False)
    n_excluded: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0
    )
    # Excluded questions by reason, adding up to `n_excluded`: a question left out because
    # nobody reviewed its evidence is not the same as one whose evidence is not there.
    excluded_reasons: Mapped[dict[str, int]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict
    )
