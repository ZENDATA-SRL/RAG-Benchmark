from __future__ import annotations

import dataclasses
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import DomainError
from src.experiments.exceptions import ExecutionNotFoundError, RunNotFoundError
from src.experiments.metrics import document_metrics, summarize
from src.experiments.models import Execution
from src.experiments.repository import (
    EvaluationRepository,
    ExecutionRepository,
    ExperimentRepository,
    RunRepository,
)
from src.experiments.seed import seed_metric_catalog
from src.infrastructure.database.enums import ExecutionStatus
from src.qa_sets.models import Question
from src.retrieval.exceptions import RetrievalBackendError
from src.retrieval.service import RetrievalService

logger = logging.getLogger(__name__)

# Why an execution is left out of the denominator of the metrics. The reason is stored on
# the evaluation, so a question that does not count is never just missing from the totals.
NOT_ANSWERABLE = "not_answerable"
NO_GOLD_DOCUMENTS = "no_gold_documents"
GOLD_NOT_IN_SNAPSHOT = "gold_document_not_in_snapshot"
EXECUTION_FAILED = "execution_failed"

ALL_SLICE = "all"
TAG_SLICE = "tag"


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
        """Mark an execution `failed` with its reason, discarding what it had retrieved."""
        execution = await self.executions.get_by_id(execution_id)
        if execution is None:
            raise ExecutionNotFoundError(execution_id)
        await self.executions.clear_calls(execution.id)
        execution.status = ExecutionStatus.FAILED
        execution.error = error
        await self.session.flush()
        return ExecutionOutcome(execution.id, ExecutionStatus.FAILED, error)


class EvaluationService:
    """Document-level scoring of executions and the aggregation of a run."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.executions = ExecutionRepository(session)
        self.experiments = ExperimentRepository(session)
        self.evaluations = EvaluationRepository(session)
        self.runs = RunRepository(session)

    async def evaluate_execution(self, execution_id: uuid.UUID) -> None:
        """Score one execution on every document-level metric, or record why it is excluded.

        The score is computed from the hits stored in the database, not from the search
        result in memory, so the same function re-scores an execution identically. A
        document is relevant if it is among the gold documents of the question, and one
        retrieved through several chunks counts once. The flag is written on each hit so the
        drill-down shows why a hit counts.

        Excluded executions get an evaluation per metric with `excluded` and the reason, and
        no score: they stay visible but do not enter the denominator. The reasons are, in
        this order: the question is not answerable, it has no gold document, a gold
        document is not in the corpus snapshot (the answer was never in the search space,
        so the retriever cannot be blamed), or the execution itself failed.

        Raises:
            ExecutionNotFoundError: If the execution does not exist.
        """
        execution = await self.executions.get_by_id(execution_id)
        if execution is None:
            raise ExecutionNotFoundError(execution_id)
        run = await self.runs.get_by_id(execution.run_id)
        experiment = await self.experiments.get_by_id(run.experiment_id)
        question = await self.session.get(Question, execution.question_id)
        definitions, evaluator = await seed_metric_catalog(self.session)
        gold = await self.experiments.gold_document_ids(question.id)

        reason = await self._exclusion_reason(
            execution, question, gold, experiment.corpus_snapshot_id
        )
        scores: dict[str, float | None] = {}
        if (
            execution.status == ExecutionStatus.SUCCEEDED
            and question.answerable
            and gold
        ):
            hits = await self.executions.hits_of_execution(execution.id)
            for hit, document_id in hits:
                hit.relevant_document = document_id in gold
            await self.session.flush()
            if reason is None:
                scores = document_metrics(
                    [document_id for _, document_id in hits], gold
                )

        rows = [
            {
                "execution_id": execution.id,
                "metric_definition_id": definition.id,
                "evaluator_id": evaluator.id,
                "score": scores.get(key),
                "excluded": reason is not None,
                "exclusion_reason": reason,
            }
            for key, definition in definitions.items()
        ]
        await self.evaluations.replace_for_execution(execution.id, evaluator.id, rows)

    async def aggregate_run(self, run_id: uuid.UUID) -> None:
        """Compute `metric_aggregates` for a run: per variant, metric and slice.

        Each variant and metric is aggregated over everything and over each question tag.
        The effective count is the number of scores that entered the statistics and the
        excluded count the evaluations that were left out, so the two together always
        account for every execution of the variant. Rewriting a run's aggregates replaces
        the previous ones, so it can be repeated.

        Raises:
            RunNotFoundError: If the run does not exist.
        """
        if await self.runs.get_by_id(run_id) is None:
            raise RunNotFoundError(run_id)
        groups: dict[
            tuple[uuid.UUID, uuid.UUID, str, str], tuple[list[float], list[int]]
        ] = {}
        for row in await self.evaluations.rows_for_run(run_id):
            slices = [(ALL_SLICE, ALL_SLICE)] + [
                (TAG_SLICE, tag) for tag in sorted(set(row.tags))
            ]
            for slice_key, slice_value in slices:
                scores, excluded = groups.setdefault(
                    (row.variant_id, row.metric_definition_id, slice_key, slice_value),
                    ([], [0]),
                )
                if row.excluded:
                    excluded[0] += 1
                elif row.score is not None:
                    scores.append(row.score)

        rows = []
        for (variant_id, metric_id, slice_key, slice_value), (
            scores,
            excluded,
        ) in groups.items():
            stats = summarize(scores)
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
                    "n_effective": len(scores),
                    "n_excluded": excluded[0],
                }
            )
        await self.evaluations.replace_aggregates(run_id, rows)

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
