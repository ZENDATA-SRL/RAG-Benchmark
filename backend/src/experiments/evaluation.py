from __future__ import annotations

import dataclasses
import datetime as dt
import logging
import statistics
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import DomainError
from src.core.hashing import hash_json
from src.experiments.exceptions import ExecutionNotFoundError, RunNotFoundError
from src.experiments.metrics import (
    CHUNK_FIRST_RELEVANT_CALL,
    CHUNK_SET_PRECISION,
    CHUNK_SET_RECALL,
    FIRST_RELEVANT_CALL,
    REFUSAL_ACCURACY,
    SET_PRECISION,
    SET_RECALL,
    GoldChunk,
    answer_metrics,
    call_efficiency,
    chunk_metrics,
    chunk_set_metrics,
    document_metrics,
    document_set_metrics,
    first_relevant_call,
    gold_chunk,
    metric_keys,
    metric_specs,
    summarize,
)
from src.experiments.models import (
    Evaluator,
    Execution,
    Experiment,
    MetricDefinition,
    RetrievalHit,
    Run,
)
from src.experiments.repository import (
    EvaluationRepository,
    EvidenceRow,
    ExecutionRepository,
    ExperimentRepository,
    RunRepository,
)
from src.experiments.seed import evaluator_name, seed_metric_catalog
from src.infrastructure.database.enums import (
    EvidenceLinkStatus,
    ExecutionStatus,
    ExperimentType,
    MetricLevel,
    RetrievalScope,
)
from src.qa_sets.models import Question
from src.qa_sets.repository import QASetSnapshotRepository, QuestionRepository
from src.retrieval.exceptions import RetrievalBackendError
from src.retrieval.service import RetrievalService

logger = logging.getLogger(__name__)

# Why an execution is left out of the denominator of the metrics. The reason is stored on
# the evaluation, so a question that does not count is never just missing from the totals.
NOT_ANSWERABLE = "not_answerable"
NO_GOLD_DOCUMENTS = "no_gold_documents"
GOLD_NOT_IN_SNAPSHOT = "gold_document_not_in_snapshot"
EXECUTION_FAILED = "execution_failed"
# Chunk level only: the evidence of the question under the variant's chunking
# configuration was not reviewed (no link, or a draft), or was looked for and not found.
EVIDENCE_NOT_REVIEWED = "evidence_not_reviewed"
EVIDENCE_NOT_FOUND = "evidence_not_found"
# Set metrics on the `cited` scope only: the answer system declares no citations, which
# says nothing about how well it attributes.
SCOPE_NOT_DECLARED = "scope_not_declared"
# Answer metrics only: the system did not say whether it refused, or how many tokens it
# used. A missing value is not a zero.
NOT_REPORTED = "not_reported"

# The order the reasons are checked in, which is also the one that names a question whose
# repetitions were excluded for different reasons.
EXCLUSION_REASONS = (
    NOT_ANSWERABLE,
    EVIDENCE_NOT_REVIEWED,
    EVIDENCE_NOT_FOUND,
    NO_GOLD_DOCUMENTS,
    GOLD_NOT_IN_SNAPSHOT,
    EXECUTION_FAILED,
    SCOPE_NOT_DECLARED,
    NOT_REPORTED,
)

# Metrics read on the scope's chunks: excluded when the scope is not declared, while the
# other Q&A metrics of the same level still count.
_SCOPE_KEYS = frozenset(
    {SET_RECALL, SET_PRECISION, CHUNK_SET_RECALL, CHUNK_SET_PRECISION}
)

ALL_SLICE = "all"
TAG_SLICE = "tag"

# Key of `runs.config_snapshot` recording the evidence the chunk metrics were computed on.
CHUNK_GOLD_KEY = "chunk_gold"


@dataclasses.dataclass(frozen=True)
class ExecutionOutcome:
    """What happened to one execution: `succeeded`, or `failed` with the reason."""

    execution_id: uuid.UUID
    status: ExecutionStatus
    error: str | None = None


class ExecutionRunner:
    """Run one execution of a retrieval experiment and score it.

    The unit the workflow repeats for every question, variant and repetition. It calls the
    same `RetrievalService.search` the retrieval endpoint exposes, in-process, so what an
    experiment measures is exactly what an answer system would be given.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.executions = ExecutionRepository(session)
        self.evaluation = EvaluationService(session)

    async def run(self, execution_id: uuid.UUID) -> ExecutionOutcome:
        """Retrieve for the question of an execution, record the hits and score them.

        An execution that already succeeded is returned as it is: this is what makes
        relaunching an interrupted run skip the work already done. What an earlier,
        interrupted attempt recorded is discarded before retrying.

        A failure of the embedder or of the vector store is raised, so the workflow retries
        it with backoff: those are the errors that can be transient. Any other domain error
        is permanent for this question, so it marks the execution `failed` with the reason
        and returns, and the run goes on with the other questions.

        Raises:
            ExecutionNotFoundError: If the execution does not exist.
            RetrievalBackendError: If the embedder or the vector store failed.
        """
        execution = await self.executions.get_by_id(execution_id)
        if execution is None:
            raise ExecutionNotFoundError(execution_id)
        if execution.status == ExecutionStatus.SUCCEEDED:
            return ExecutionOutcome(execution.id, ExecutionStatus.SUCCEEDED)

        question = await self.session.get(Question, execution.question_id)
        variant = await ExperimentRepository(self.session).get_variant(
            execution.variant_id
        )
        execution.status = ExecutionStatus.RUNNING
        await self.executions.clear_calls(execution.id)
        await self.session.flush()

        try:
            result = await RetrievalService(self.session).search(
                index_build_id=variant.index_build_id,
                retrieval_profile_id=variant.retrieval_profile_id,
                query=question.text,
                execution_id=execution.id,
            )
        except RetrievalBackendError:
            raise
        except DomainError as error:
            return await self.fail(execution.id, error.message)

        execution.status = ExecutionStatus.SUCCEEDED
        execution.error = None
        execution.timings = dataclasses.asdict(result.timings)
        await self.session.flush()
        await self.evaluation.evaluate_execution(execution.id)
        return ExecutionOutcome(execution.id, ExecutionStatus.SUCCEEDED)

    async def fail(self, execution_id: uuid.UUID, error: str) -> ExecutionOutcome:
        """Mark an execution `failed` with its reason, discarding what it had produced."""
        execution = await self.executions.get_by_id(execution_id)
        if execution is None:
            raise ExecutionNotFoundError(execution_id)
        await self.executions.clear_calls(execution.id)
        clear_answer(execution)
        execution.status = ExecutionStatus.FAILED
        execution.error = error
        await self.session.flush()
        return ExecutionOutcome(execution.id, ExecutionStatus.FAILED, error)


def clear_answer(execution: Execution) -> None:
    """Forget the answer an earlier attempt of an execution recorded."""
    execution.answer_text = None
    execution.refused = None
    execution.usage = None
    execution.cited_chunk_ids = None


@dataclasses.dataclass(frozen=True)
class _Evidence:
    """The evidence of a question under one chunking configuration."""

    status: EvidenceLinkStatus | None
    chunks: dict[uuid.UUID, GoldChunk]


class EvaluationService:
    """Scoring of executions at document and chunk level, and the aggregation of a run."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.executions = ExecutionRepository(session)
        self.experiments = ExperimentRepository(session)
        self.evaluations = EvaluationRepository(session)
        self.runs = RunRepository(session)
        self._catalog: (
            tuple[dict[str, MetricDefinition], dict[str, Evaluator]] | None
        ) = None

    async def evaluate_execution(self, execution_id: uuid.UUID) -> None:
        """Score one execution on the metrics of its experiment's type, or record why not.

        The score is computed from the hits stored in the database, not from the search
        result in memory, so the same function re-scores an execution identically, and
        re-scoring after the evidence changed needs no new retrieval.

        At document level a chunk is relevant if its document is a gold document of the
        question. At chunk level it is relevant if it is a confirmed evidence chunk of the
        question under the chunking configuration the variant searches: evidence confirmed
        under another configuration says nothing about these chunks. Both flags are written
        on each hit so the drill-down shows why a hit counts.

        The ranked metrics (cutoffs and ranks) are computed on the first call: several
        calls give several lists whose ranks and scores do not compare, and with one call,
        as in a retrieval experiment, this is every hit. A Q&A experiment is also scored on
        the distinct chunks of its scope (what was retrieved, or what the system cited),
        on the call where the first relevant chunk arrived, and on the efficiency of its
        calls, repetitions included, and on what the answer says: whether it refused when
        it should have, its latency and its tokens. A retrieval experiment does not get
        those metrics at all: with one call the retrieval ones would only repeat the ranked
        ones or be constants, and there is no answer.

        Excluded executions get an evaluation per metric with `excluded` and the reason, and
        no score: they stay visible but do not enter the denominator. At document level the
        reasons are, in this order: the question is not answerable, it has no gold
        document, a gold document is not in the corpus snapshot (the answer was never in
        the search space, so the retriever cannot be blamed), or the execution itself
        failed. At chunk level the evidence not being reviewed, or not found, comes right
        after the question not being answerable: a question can count for its documents and
        be left out for its chunks. The set metrics on the `cited` scope are also excluded
        when the system declared no citations. The efficiency and the answer metrics read
        no gold, so they count every question, the unanswerable ones included: they are
        excluded when the execution failed, and an answer metric also when the system did
        not report the value. The refusal accuracy also leaves out a question whose gold
        document is not in the snapshot, since there refusing is the right answer.

        Raises:
            ExecutionNotFoundError: If the execution does not exist.
        """
        execution = await self.executions.get_by_id(execution_id)
        if execution is None:
            raise ExecutionNotFoundError(execution_id)
        run = await self.runs.get_by_id(execution.run_id)
        experiment = await self.experiments.get_by_id(run.experiment_id)
        question = await self.session.get(Question, execution.question_id)
        definitions, evaluators = await self._metric_catalog()
        keys = metric_keys(experiment.type)
        is_qa = experiment.type == ExperimentType.QA
        gold = await self.experiments.gold_document_ids(question.id)
        evidence = await self._evidence(question.id, execution.variant_id)

        document_reason = await self._exclusion_reason(
            execution, question, gold, experiment.corpus_snapshot_id
        )
        chunk_reason = _chunk_exclusion_reason(question, evidence, document_reason)
        scope_declared = (
            experiment.retrieval_scope != RetrievalScope.CITED
            or execution.cited_chunk_ids is not None
        )
        succeeded = execution.status == ExecutionStatus.SUCCEEDED
        scores: dict[str, float | None] = {}
        if succeeded:
            hits = await self.executions.hits_of_execution(execution.id)
            calls = await self.executions.call_indices(execution.id)
            for hit, document_id, _ in hits:
                if question.answerable and gold:
                    hit.relevant_document = document_id in gold
                hit.relevant_chunk = (
                    hit.chunk_id in evidence.chunks if chunk_reason is None else None
                )
            await self.session.flush()
            first = [
                (hit, document)
                for hit, document, call in hits
                if calls and call == calls[0]
            ]
            if document_reason is None:
                scores.update(document_metrics([doc for _, doc in first], gold))
            if chunk_reason is None:
                scores.update(
                    chunk_metrics([hit.chunk_id for hit, _ in first], evidence.chunks)
                )
            if is_qa:
                scores.update(
                    await self._qa_scores(
                        execution,
                        experiment.retrieval_scope,
                        calls,
                        hits,
                        gold if document_reason is None else None,
                        evidence.chunks if chunk_reason is None else None,
                    )
                )

        if is_qa and succeeded:
            scores.update(
                answer_metrics(
                    refused=execution.refused,
                    answerable=question.answerable,
                    usage=execution.usage,
                    timings=execution.timings,
                )
            )

        rows: dict[str, list[dict]] = {name: [] for name in evaluators}
        for spec in metric_specs():
            if spec.key not in keys:
                continue
            if spec.level is None:
                # Read no gold: only a failure, or an answer that does not say, excludes.
                if not succeeded:
                    reason = EXECUTION_FAILED
                elif (
                    spec.key == REFUSAL_ACCURACY
                    and document_reason == GOLD_NOT_IN_SNAPSHOT
                ):
                    # The answer was never searchable: refusing is right, and the label
                    # "answerable" would score it as wrong.
                    reason = GOLD_NOT_IN_SNAPSHOT
                elif spec.evaluator is not None and scores.get(spec.key) is None:
                    reason = NOT_REPORTED
                else:
                    reason = None
            else:
                reason = (
                    document_reason
                    if spec.level == MetricLevel.DOCUMENT
                    else chunk_reason
                )
                if reason is None and spec.key in _SCOPE_KEYS and not scope_declared:
                    reason = SCOPE_NOT_DECLARED
            name = evaluator_name(spec)
            rows[name].append(
                {
                    "execution_id": execution.id,
                    "metric_definition_id": definitions[spec.key].id,
                    "evaluator_id": evaluators[name].id,
                    "score": scores.get(spec.key) if reason is None else None,
                    "excluded": reason is not None,
                    "exclusion_reason": reason,
                }
            )
        for name, evaluator in evaluators.items():
            await self.evaluations.replace_for_execution(
                execution.id, evaluator.id, rows[name]
            )

    async def _qa_scores(
        self,
        execution: Execution,
        scope: RetrievalScope,
        calls: list[int],
        hits: list[tuple[RetrievalHit, uuid.UUID | None, int]],
        gold: set[uuid.UUID] | None,
        evidence: dict[uuid.UUID, GoldChunk] | None,
    ) -> dict[str, float | None]:
        """The set, first-call and efficiency scores of a Q&A execution.

        `gold` and `evidence` are `None` when their level is excluded, so only the scores
        that will count are computed.
        """
        scores = call_efficiency(len(calls), [hit.chunk_id for hit, _, _ in hits])

        # The scope as distinct chunks with their document. A hit whose chunk is no longer
        # known cannot be told apart from another, so each such hit stays in the set.
        scope_chunks: list[tuple[uuid.UUID | None, uuid.UUID | None]] = []
        if scope == RetrievalScope.CITED:
            cited = list(dict.fromkeys(execution.cited_chunk_ids or []))
            known = await self.executions.chunk_documents(cited)
            scope_chunks = [(chunk_id, known.get(chunk_id)) for chunk_id in cited]
        else:
            seen: set[uuid.UUID] = set()
            for hit, document_id, _ in hits:
                if hit.chunk_id is not None:
                    if hit.chunk_id in seen:
                        continue
                    seen.add(hit.chunk_id)
                scope_chunks.append((hit.chunk_id, document_id))

        per_call: dict[int, list[tuple[RetrievalHit, uuid.UUID | None]]] = {
            call: [] for call in calls
        }
        for hit, document_id, call in hits:
            per_call.setdefault(call, []).append((hit, document_id))
        if gold is not None:
            scores.update(document_set_metrics([doc for _, doc in scope_chunks], gold))
            scores[FIRST_RELEVANT_CALL] = first_relevant_call(
                [[doc in gold for _, doc in items] for items in per_call.values()]
            )
        if evidence is not None:
            scores.update(
                chunk_set_metrics([chunk for chunk, _ in scope_chunks], evidence)
            )
            scores[CHUNK_FIRST_RELEVANT_CALL] = first_relevant_call(
                [
                    [hit.chunk_id in evidence for hit, _ in items]
                    for items in per_call.values()
                ]
            )
        return scores

    async def aggregate_run(self, run_id: uuid.UUID) -> None:
        """Compute `metric_aggregates` for a run: per variant, metric and slice.

        Each variant and metric is aggregated over everything and over each question tag.
        The repetitions of a question are averaged first and the statistics are taken
        across questions, so a question asked five times weighs as much as one asked once,
        and the effective count is a number of questions. A question counts when at least
        one of its repetitions has a score, and is excluded when every repetition is, under
        the first of their reasons; the excluded counts are kept per reason. Rewriting a
        run's aggregates replaces the previous ones, so it can be repeated.

        Raises:
            RunNotFoundError: If the run does not exist.
        """
        if await self.runs.get_by_id(run_id) is None:
            raise RunNotFoundError(run_id)
        # Per group, per question: the scores of its repetitions and their reasons.
        groups: dict[
            tuple[uuid.UUID, uuid.UUID, str, str],
            dict[uuid.UUID, tuple[list[float], list[str]]],
        ] = {}
        for row in await self.evaluations.rows_for_run(run_id):
            slices = [(ALL_SLICE, ALL_SLICE)] + [
                (TAG_SLICE, tag) for tag in sorted(set(row.tags))
            ]
            for slice_key, slice_value in slices:
                questions = groups.setdefault(
                    (row.variant_id, row.metric_definition_id, slice_key, slice_value),
                    {},
                )
                scores, reasons = questions.setdefault(row.question_id, ([], []))
                if row.excluded:
                    reasons.append(row.exclusion_reason or "")
                elif row.score is not None:
                    scores.append(row.score)

        rows = []
        for (
            variant_id,
            metric_id,
            slice_key,
            slice_value,
        ), questions in groups.items():
            means: list[float] = []
            excluded: dict[str, int] = {}
            for scores, reasons in questions.values():
                if scores:
                    means.append(statistics.fmean(scores))
                elif reasons:
                    reason = min(reasons, key=_reason_order)
                    excluded[reason] = excluded.get(reason, 0) + 1
            stats = summarize(means)
            rows.append(
                {
                    "run_id": run_id,
                    "variant_id": variant_id,
                    "metric_definition_id": metric_id,
                    "slice_key": slice_key,
                    "slice_value": slice_value,
                    "mean": stats.mean,
                    "stddev": stats.stddev,
                    "median": stats.median,
                    "p95": stats.p95,
                    "n_effective": len(means),
                    "n_excluded": sum(excluded.values()),
                    "excluded_reasons": excluded,
                }
            )
        await self.evaluations.replace_aggregates(run_id, rows)

    async def record_chunk_gold(self, run: Run, experiment: Experiment) -> None:
        """Write on the run the evidence its chunk metrics were computed on.

        The evidence keeps changing after a QA set is frozen, as people annotate, so the
        same run can give other chunk numbers tomorrow. The run therefore records, in its
        `config_snapshot`, every link it read with its status, the counts per chunking
        configuration, the time, and a fingerprint of the links and their chunks: two
        evaluations with the same fingerprint used the same gold.
        """
        variants = await self.experiments.list_variants(experiment.id)
        configurations = sorted(
            set(
                (
                    await self.experiments.variant_configurations(
                        [variant.id for variant in variants]
                    )
                ).values()
            ),
            key=str,
        )
        question_ids = await QASetSnapshotRepository(self.session).question_ids(
            experiment.qa_set_snapshot_id
        )
        answerable = {
            question.id
            for question in await QuestionRepository(self.session).list_by_ids(
                question_ids
            )
            if question.answerable
        }
        rows = await self.experiments.evidence_rows(question_ids, configurations)
        run.config_snapshot = {
            **run.config_snapshot,
            CHUNK_GOLD_KEY: chunk_gold_record(rows, configurations, answerable),
        }
        await self.session.flush()

    async def _metric_catalog(
        self,
    ) -> tuple[dict[str, MetricDefinition], dict[MetricLevel | None, Evaluator]]:
        # Seeded once per service: a run re-scores many executions in one session.
        if self._catalog is None:
            self._catalog = await seed_metric_catalog(self.session)
        return self._catalog

    async def _evidence(
        self, question_id: uuid.UUID, variant_id: uuid.UUID
    ) -> _Evidence:
        configuration_id = (
            await self.experiments.variant_configurations([variant_id])
        )[variant_id]
        rows = await self.experiments.evidence_rows([question_id], [configuration_id])
        if not rows:
            return _Evidence(status=None, chunks={})
        return _Evidence(
            status=rows[0].status,
            chunks={
                row.chunk_id: gold_chunk(row.relevance.value, row.graded_relevance)
                for row in rows
                if row.chunk_id is not None
            },
        )

    async def _exclusion_reason(
        self,
        execution: Execution,
        question: Question,
        gold: set[uuid.UUID],
        corpus_snapshot_id: uuid.UUID,
    ) -> str | None:
        if not question.answerable:
            return NOT_ANSWERABLE
        if not gold:
            return NO_GOLD_DOCUMENTS
        if await self.experiments.gold_outside_snapshot(
            question.id, corpus_snapshot_id
        ):
            return GOLD_NOT_IN_SNAPSHOT
        if execution.status != ExecutionStatus.SUCCEEDED:
            return EXECUTION_FAILED
        return None


def chunk_gold_record(
    rows: list[EvidenceRow],
    configurations: list[uuid.UUID],
    answerable: set[uuid.UUID],
) -> dict[str, Any]:
    """The record of the evidence a run was scored on, with its fingerprint.

    Args:
        rows: The evidence rows of the run's questions under its configurations.
        configurations: The chunking configurations the run's variants search.
        answerable: The answerable questions of the run, on which the counts are taken.
    """
    links: dict[uuid.UUID, dict[str, Any]] = {}
    for row in rows:
        link = links.setdefault(
            row.link_id,
            {
                "id": str(row.link_id),
                "question_id": str(row.question_id),
                "chunking_configuration_id": str(row.chunking_configuration_id),
                "status": row.status.value,
                "chunks": [],
            },
        )
        if row.chunk_id is not None:
            link["chunks"].append(
                [str(row.chunk_id), row.relevance.value, row.graded_relevance]
            )

    counts = {}
    for configuration_id in configurations:
        statuses = [
            link["status"]
            for link in links.values()
            if link["chunking_configuration_id"] == str(configuration_id)
            and uuid.UUID(link["question_id"]) in answerable
        ]
        counts[str(configuration_id)] = {
            "answerable": len(answerable),
            "confirmed": statuses.count(EvidenceLinkStatus.CONFIRMED.value),
            "not_found": statuses.count(EvidenceLinkStatus.NOT_FOUND.value),
            "to_review": statuses.count(EvidenceLinkStatus.TO_REVIEW.value),
            "not_reviewed": len(answerable) - len(statuses),
        }
    ordered = sorted(
        links.values(),
        key=lambda link: (link["question_id"], link["chunking_configuration_id"]),
    )
    return {
        "evaluated_at": dt.datetime.now(dt.UTC).isoformat(),
        "hash": hash_json(
            [
                [
                    link["question_id"],
                    link["chunking_configuration_id"],
                    link["status"],
                    link["chunks"],
                ]
                for link in ordered
            ]
        ),
        "configurations": counts,
        "links": [
            {key: link[key] for key in ("id", "question_id", "status")}
            | {"chunking_configuration_id": link["chunking_configuration_id"]}
            for link in ordered
        ],
    }


def _chunk_exclusion_reason(
    question: Question, evidence: _Evidence, document_reason: str | None
) -> str | None:
    if not question.answerable:
        return NOT_ANSWERABLE
    if evidence.status is None or evidence.status == EvidenceLinkStatus.TO_REVIEW:
        return EVIDENCE_NOT_REVIEWED
    if evidence.status == EvidenceLinkStatus.NOT_FOUND:
        return EVIDENCE_NOT_FOUND
    if not evidence.chunks:
        return EVIDENCE_NOT_REVIEWED
    if document_reason in (GOLD_NOT_IN_SNAPSHOT, EXECUTION_FAILED):
        return document_reason
    return None


def _reason_order(reason: str) -> int:
    return (
        EXCLUSION_REASONS.index(reason)
        if reason in EXCLUSION_REASONS
        else len(EXCLUSION_REASONS)
    )
