from __future__ import annotations

import csv
import io
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.corpora.repository import CorpusSnapshotRepository
from src.experiments.exceptions import QuestionNotInRunError
from src.experiments.metrics import FIRST_RELEVANT_RANK, metric_specs
from src.experiments.repository import (
    EvaluationRepository,
    ExecutionRepository,
)
from src.experiments.schemas import (
    ExecutionDetailRead,
    HitDetailRead,
    MetricResultRead,
    QuestionDrilldownRead,
    QuestionVariantOutcomeRead,
    RunQuestionRead,
    RunResultsRead,
    SnapshotDeclaredRead,
    UncoveredDocumentRead,
    VariantDrilldownRead,
    VariantResultRead,
)
from src.experiments.service import ExperimentService, RunService
from src.qa_sets.repository import QASetSnapshotRepository, QuestionRepository

CSV_COLUMNS = (
    "variant",
    "is_baseline",
    "metric",
    "mean",
    "stddev",
    "median",
    "p95",
    "n_effective",
    "n_excluded",
    "corpus_snapshot_id",
    "qa_set_snapshot_id",
)


class ResultsService:
    """The read side of a run: aggregated metrics and the per-question drill-down."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.runs = RunService(session)
        self.experiments = ExperimentService(session)
        self.evaluations = EvaluationRepository(session)
        self.executions = ExecutionRepository(session)
        self.questions = QuestionRepository(session)
        self.qa_snapshots = QASetSnapshotRepository(session)

    async def results(
        self,
        experiment_id: uuid.UUID,
        run_id: uuid.UUID,
        *,
        slice_key: str = "all",
        slice_value: str = "all",
    ) -> RunResultsRead:
        """Aggregated metrics per variant, with the snapshots they were computed on.

        Every metric carries its effective and excluded counts: a mean without the number
        of questions behind it cannot be compared with another.

        Raises:
            RunNotFoundError: If the run does not exist or belongs to another experiment.
        """
        run = await self.runs.get(run_id, experiment_id)
        experiment = await self.experiments.get(experiment_id)
        definitions = await self.evaluations.metric_definitions()
        by_id = {definition.id: definition for definition in definitions.values()}
        order = {spec.key: index for index, spec in enumerate(metric_specs())}
        aggregates = await self.evaluations.aggregates_for_run(
            run_id, slice_key=slice_key, slice_value=slice_value
        )
        per_variant: dict[uuid.UUID, list[MetricResultRead]] = {}
        for aggregate in aggregates:
            definition = by_id[aggregate.metric_definition_id]
            per_variant.setdefault(aggregate.variant_id, []).append(
                MetricResultRead(
                    key=definition.key,
                    direction=definition.direction,
                    mean=aggregate.mean,
                    stddev=aggregate.stddev,
                    median=aggregate.median,
                    p95=aggregate.p95,
                    n_effective=aggregate.n_effective,
                    n_excluded=aggregate.n_excluded,
                )
            )

        corpus_snapshot = await CorpusSnapshotRepository(self.session).get_by_id(
            experiment.corpus_snapshot_id
        )
        qa_snapshot = await self.qa_snapshots.get_by_id(experiment.qa_set_snapshot_id)
        variants = []
        for view in await self.experiments.variant_views(experiment_id):
            metrics = sorted(
                per_variant.get(view.variant.id, []),
                key=lambda metric: order[metric.key],
            )
            variants.append(
                VariantResultRead(
                    variant_id=view.variant.id,
                    name=view.variant.name,
                    is_baseline=view.variant.is_baseline,
                    index_build_id=view.index_build.id,
                    retrieval_profile_id=view.retrieval_profile.id,
                    top_k=view.retrieval_profile.top_k,
                    metrics=metrics,
                )
            )
        return RunResultsRead(
            run_id=run.id,
            experiment_id=experiment_id,
            status=run.status,
            repetitions=experiment.repetitions,
            question_count=qa_snapshot.question_count,
            corpus_snapshot=SnapshotDeclaredRead(
                id=corpus_snapshot.id,
                label=corpus_snapshot.label,
                document_count=corpus_snapshot.document_count,
                corpus_id=corpus_snapshot.corpus_id,
            ),
            qa_set_snapshot=SnapshotDeclaredRead(
                id=qa_snapshot.id,
                label=qa_snapshot.label,
                question_count=qa_snapshot.question_count,
            ),
            slice_key=slice_key,
            slice_value=slice_value,
            variants=variants,
        )

    async def results_csv(self, experiment_id: uuid.UUID, run_id: uuid.UUID) -> str:
        """The aggregated metrics of a run as CSV: one row per variant and metric."""
        results = await self.results(experiment_id, run_id)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(CSV_COLUMNS)
        for variant in results.variants:
            for metric in variant.metrics:
                writer.writerow(
                    [
                        variant.name,
                        variant.is_baseline,
                        metric.key,
                        metric.mean,
                        metric.stddev,
                        metric.median,
                        metric.p95,
                        metric.n_effective,
                        metric.n_excluded,
                        results.corpus_snapshot.id,
                        results.qa_set_snapshot.id,
                    ]
                )
        return buffer.getvalue()

    async def list_questions(
        self,
        experiment_id: uuid.UUID,
        run_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[RunQuestionRead], int]:
        """A page of the questions of a run with the outcome of each variant.

        The outcome is the first repetition's: the table is where one picks a question to
        open, and the drill-down shows every repetition.
        """
        await self.runs.get(run_id, experiment_id)
        experiment = await self.experiments.get(experiment_id)
        question_ids = await self.qa_snapshots.question_ids(
            experiment.qa_set_snapshot_id
        )
        page_ids = question_ids[offset : offset + limit]
        questions = {
            question.id: question
            for question in await self.questions.list_by_ids(page_ids)
        }
        executions = await self.executions.question_row_executions(run_id, page_ids)
        evaluations = await self.evaluations.evaluations_of_executions(
            [execution.id for execution in executions]
        )
        definitions = await self.evaluations.metric_definitions()
        rank_id = definitions[FIRST_RELEVANT_RANK].id
        reasons: dict[uuid.UUID, str | None] = {}
        ranks: dict[uuid.UUID, float | None] = {}
        for evaluation in evaluations:
            if evaluation.metric_definition_id == rank_id:
                reasons[evaluation.execution_id] = evaluation.exclusion_reason
                ranks[evaluation.execution_id] = evaluation.score

        variant_order = [
            view.variant.id
            for view in await self.experiments.variant_views(experiment_id)
        ]
        by_question: dict[uuid.UUID, dict[uuid.UUID, QuestionVariantOutcomeRead]] = {}
        for execution in executions:
            by_question.setdefault(execution.question_id, {})[execution.variant_id] = (
                QuestionVariantOutcomeRead(
                    variant_id=execution.variant_id,
                    status=execution.status,
                    first_relevant_rank=ranks.get(execution.id),
                    excluded_reason=reasons.get(execution.id),
                )
            )
        rows = []
        for question_id in page_ids:
            question = questions[question_id]
            outcomes = by_question.get(question_id, {})
            rows.append(
                RunQuestionRead(
                    question_id=question_id,
                    text=question.text,
                    tags=list(question.tags),
                    answerable=question.answerable,
                    outcomes=[
                        outcomes[variant_id]
                        for variant_id in variant_order
                        if variant_id in outcomes
                    ],
                )
            )
        return rows, len(question_ids)

    async def question_detail(
        self, experiment_id: uuid.UUID, run_id: uuid.UUID, question_id: uuid.UUID
    ) -> QuestionDrilldownRead:
        """What each variant retrieved for a question, hit by hit.

        Raises:
            RunNotFoundError: If the run does not exist or belongs to another experiment.
            QuestionNotInRunError: If the run did not evaluate the question.
        """
        await self.runs.get(run_id, experiment_id)
        executions = await self.executions.list_for_question(run_id, question_id)
        if not executions:
            raise QuestionNotInRunError(run_id, question_id)
        question = (await self.questions.list_by_ids([question_id]))[0]
        gold = (await self.questions.gold_by_question([question_id])).get(
            question_id, []
        )

        definitions = await self.evaluations.metric_definitions()
        rank_id = definitions[FIRST_RELEVANT_RANK].id
        reasons = {
            evaluation.execution_id: evaluation.exclusion_reason
            for evaluation in await self.evaluations.evaluations_of_executions(
                [execution.id for execution in executions]
            )
            if evaluation.metric_definition_id == rank_id
        }
        hits: dict[uuid.UUID, list[HitDetailRead]] = {}
        for (
            execution_id,
            hit,
            chunk,
            document_id,
            filename,
        ) in await self.executions.hit_details(
            [execution.id for execution in executions]
        ):
            page = chunk.chunk_metadata.get("page") if chunk is not None else None
            hits.setdefault(execution_id, []).append(
                HitDetailRead(
                    rank=hit.rank,
                    score=hit.score,
                    chunk_id=hit.chunk_id,
                    document_id=document_id,
                    filename=filename,
                    ordinal=chunk.ordinal if chunk is not None else None,
                    page=page if isinstance(page, int) else None,
                    text=chunk.text if chunk is not None else None,
                    relevant_document=hit.relevant_document,
                )
            )

        variants = []
        for view in await self.experiments.variant_views(experiment_id):
            variants.append(
                VariantDrilldownRead(
                    variant_id=view.variant.id,
                    name=view.variant.name,
                    is_baseline=view.variant.is_baseline,
                    executions=[
                        ExecutionDetailRead(
                            execution_id=execution.id,
                            repetition=execution.repetition,
                            status=execution.status,
                            error=execution.error,
                            excluded_reason=reasons.get(execution.id),
                            timings=execution.timings,
                            hits=hits.get(execution.id, []),
                        )
                        for execution in executions
                        if execution.variant_id == view.variant.id
                    ],
                )
            )
        return QuestionDrilldownRead(
            run_id=run_id,
            question_id=question_id,
            text=question.text,
            tags=list(question.tags),
            answerable=question.answerable,
            gold_documents=[
                UncoveredDocumentRead(document_id=document_id, filename=filename)
                for document_id, filename in gold
            ],
            variants=variants,
        )
