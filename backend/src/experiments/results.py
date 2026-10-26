from __future__ import annotations

import csv
import io
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.corpora.repository import CorpusSnapshotRepository
from src.experiments.evaluation import CHUNK_GOLD_KEY
from src.experiments.exceptions import QuestionNotInRunError
from src.experiments.metrics import (
    CHUNK_FIRST_RELEVANT_RANK,
    FIRST_RELEVANT_RANK,
    metric_specs,
)
from src.experiments.repository import (
    EvaluationRepository,
    ExecutionRepository,
)
from src.experiments.schemas import (
    ChunkGoldRead,
    CrossGroupRead,
    EvidenceCountsRead,
    ExecutionDetailRead,
    GoldChunkRead,
    HitDetailRead,
    MetricResultRead,
    QuestionDrilldownRead,
    QuestionVariantOutcomeRead,
    ResultGroupRead,
    RunQuestionRead,
    RunResultsRead,
    SnapshotDeclaredRead,
    UncoveredDocumentRead,
    VariantDrilldownRead,
    VariantResultRead,
)
from src.experiments.service import ExperimentService, RunService
from src.infrastructure.database.enums import EvidenceLinkStatus, MetricLevel
from src.pipelines.service import ChunkingConfigurationService, ProfileService
from src.qa_sets.repository import (
    EvidenceRepository,
    QASetSnapshotRepository,
    QuestionRepository,
)
from src.qa_sets.service import NOT_REVIEWED
from src.qa_sets.utils import recall_ceiling

CSV_COLUMNS = (
    "chunking_configuration_id",
    "variant",
    "is_baseline",
    "level",
    "metric",
    "mean",
    "stddev",
    "median",
    "p95",
    "n_effective",
    "n_excluded",
    "excluded_reasons",
    "corpus_snapshot_id",
    "qa_set_snapshot_id",
)


CROSS_GROUP_REASON = (
    "Chunk-level metrics are computed against evidence confirmed on the chunks of one "
    "chunking configuration, so they only compare variants that search the same "
    "configuration. Across configurations only document-level metrics compare."
)


def _page(chunk) -> int | None:
    page = chunk.chunk_metadata.get("page") if chunk is not None else None
    return page if isinstance(page, int) else None


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
        """Aggregated metrics per variant, grouped by the chunking configuration searched.

        Every metric carries its effective and excluded counts, the latter per reason: a
        mean without the number of questions behind it cannot be compared with another.
        Each group states how far the evidence of its configuration had been reviewed when
        the run was scored, and the recall ceiling that follows from it.

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
                    level=definition.level or MetricLevel.DOCUMENT,
                    direction=definition.direction,
                    mean=aggregate.mean,
                    stddev=aggregate.stddev,
                    median=aggregate.median,
                    p95=aggregate.p95,
                    n_effective=aggregate.n_effective,
                    n_excluded=aggregate.n_excluded,
                    excluded_reasons=dict(aggregate.excluded_reasons or {}),
                )
            )

        chunk_gold = run.config_snapshot.get(CHUNK_GOLD_KEY)
        groups: dict[uuid.UUID, ResultGroupRead] = {}
        for view in await self.experiments.variant_views(experiment_id):
            configuration_id = view.index_build.chunking_configuration_id
            if configuration_id not in groups:
                groups[configuration_id] = await self._group(
                    configuration_id, chunk_gold
                )
            groups[configuration_id].variants.append(
                VariantResultRead(
                    variant_id=view.variant.id,
                    name=view.variant.name,
                    is_baseline=view.variant.is_baseline,
                    index_build_id=view.index_build.id,
                    retrieval_profile_id=view.retrieval_profile.id,
                    top_k=view.retrieval_profile.top_k,
                    metrics=sorted(
                        per_variant.get(view.variant.id, []),
                        key=lambda metric: order.get(metric.key, len(order)),
                    ),
                )
            )

        corpus_snapshot = await CorpusSnapshotRepository(self.session).get_by_id(
            experiment.corpus_snapshot_id
        )
        qa_snapshot = await self.qa_snapshots.get_by_id(experiment.qa_set_snapshot_id)
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
            chunk_gold=ChunkGoldRead(
                evaluated_at=chunk_gold["evaluated_at"], hash=chunk_gold["hash"]
            )
            if chunk_gold
            else None,
            cross_group_metrics=CrossGroupRead(
                keys=[
                    spec.key
                    for spec in metric_specs()
                    if spec.level == MetricLevel.DOCUMENT
                ],
                reason=CROSS_GROUP_REASON,
            ),
            groups=list(groups.values()),
        )

    async def results_csv(self, experiment_id: uuid.UUID, run_id: uuid.UUID) -> str:
        """The aggregated metrics of a run as CSV: one row per variant and metric.

        Each row names the chunking configuration and the level, so a chunk-level row is
        never compared with one of another configuration by mistake.
        """
        results = await self.results(experiment_id, run_id)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(CSV_COLUMNS)
        for group in results.groups:
            for variant in group.variants:
                for metric in variant.metrics:
                    writer.writerow(
                        [
                            group.chunking_configuration_id,
                            variant.name,
                            variant.is_baseline,
                            metric.level.value,
                            metric.key,
                            metric.mean,
                            metric.stddev,
                            metric.median,
                            metric.p95,
                            metric.n_effective,
                            metric.n_excluded,
                            "|".join(
                                f"{reason}={count}"
                                for reason, count in sorted(
                                    metric.excluded_reasons.items()
                                )
                            ),
                            results.corpus_snapshot.id,
                            results.qa_set_snapshot.id,
                        ]
                    )
        return buffer.getvalue()

    async def _group(
        self, configuration_id: uuid.UUID, chunk_gold: dict | None
    ) -> ResultGroupRead:
        configuration = await ChunkingConfigurationService(self.session).get(
            configuration_id
        )
        profiles = ProfileService(self.session)
        parsing = await profiles.get_parsing_profile(configuration.parsing_profile_id)
        chunking = await profiles.get_chunking_profile(
            configuration.chunking_profile_id
        )
        counts = (chunk_gold or {}).get("configurations", {}).get(str(configuration_id))
        return ResultGroupRead(
            chunking_configuration_id=configuration_id,
            chunking_configuration_name=configuration.name,
            parsing=parsing.name,
            chunking=chunking.name,
            evidence_coverage=EvidenceCountsRead(**counts) if counts else None,
            recall_ceiling=recall_ceiling(counts["confirmed"], counts["not_found"])
            if counts
            else None,
            variants=[],
        )

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
        chunk_rank_id = definitions[CHUNK_FIRST_RELEVANT_RANK].id
        # Per execution and level: the rank of the first relevant chunk, or the reason
        # the execution does not count.
        outcomes: dict[
            tuple[uuid.UUID, uuid.UUID], tuple[float | None, str | None]
        ] = {}
        for evaluation in evaluations:
            if evaluation.metric_definition_id in (rank_id, chunk_rank_id):
                outcomes[(evaluation.execution_id, evaluation.metric_definition_id)] = (
                    evaluation.score,
                    evaluation.exclusion_reason,
                )

        variant_order = [
            view.variant.id
            for view in await self.experiments.variant_views(experiment_id)
        ]
        by_question: dict[uuid.UUID, dict[uuid.UUID, QuestionVariantOutcomeRead]] = {}
        for execution in executions:
            rank, reason = outcomes.get((execution.id, rank_id), (None, None))
            chunk_rank, chunk_reason = outcomes.get(
                (execution.id, chunk_rank_id), (None, None)
            )
            by_question.setdefault(execution.question_id, {})[execution.variant_id] = (
                QuestionVariantOutcomeRead(
                    variant_id=execution.variant_id,
                    status=execution.status,
                    first_relevant_rank=rank,
                    excluded_reason=reason,
                    chunk_first_relevant_rank=chunk_rank,
                    chunk_excluded_reason=chunk_reason,
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

        Each hit says whether its document is gold and whether the chunk itself is an
        evidence chunk under the variant's configuration, as of the last scoring. Each
        variant also lists the evidence chunks of that configuration as they are now, the
        ones it did not retrieve included, which is what the annotation page links to.

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
        chunk_rank_id = definitions[CHUNK_FIRST_RELEVANT_RANK].id
        reasons: dict[tuple[uuid.UUID, uuid.UUID], str | None] = {
            (evaluation.execution_id, evaluation.metric_definition_id): (
                evaluation.exclusion_reason
            )
            for evaluation in await self.evaluations.evaluations_of_executions(
                [execution.id for execution in executions]
            )
            if evaluation.metric_definition_id in (rank_id, chunk_rank_id)
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
            hits.setdefault(execution_id, []).append(
                HitDetailRead(
                    rank=hit.rank,
                    score=hit.score,
                    chunk_id=hit.chunk_id,
                    document_id=document_id,
                    filename=filename,
                    ordinal=chunk.ordinal if chunk is not None else None,
                    page=_page(chunk),
                    text=chunk.text if chunk is not None else None,
                    relevant_document=hit.relevant_document,
                    relevant_chunk=hit.relevant_chunk,
                )
            )

        variants = []
        for view in await self.experiments.variant_views(experiment_id):
            own = [
                execution
                for execution in executions
                if execution.variant_id == view.variant.id
            ]
            status, gold_chunks = await self._evidence(
                question_id,
                view.index_build.chunking_configuration_id,
                retrieved={
                    hit.chunk_id
                    for execution in own
                    for hit in hits.get(execution.id, [])
                },
            )
            grades = {chunk.chunk_id: chunk.relevance for chunk in gold_chunks}
            variants.append(
                VariantDrilldownRead(
                    variant_id=view.variant.id,
                    name=view.variant.name,
                    is_baseline=view.variant.is_baseline,
                    chunking_configuration_id=view.index_build.chunking_configuration_id,
                    evidence_status=status,
                    gold_chunks=gold_chunks,
                    executions=[
                        ExecutionDetailRead(
                            execution_id=execution.id,
                            repetition=execution.repetition,
                            status=execution.status,
                            error=execution.error,
                            excluded_reason=reasons.get((execution.id, rank_id)),
                            chunk_excluded_reason=reasons.get(
                                (execution.id, chunk_rank_id)
                            ),
                            timings=execution.timings,
                            hits=[
                                hit.model_copy(
                                    update={"relevance": grades.get(hit.chunk_id)}
                                )
                                for hit in hits.get(execution.id, [])
                            ],
                        )
                        for execution in own
                    ],
                )
            )
        return QuestionDrilldownRead(
            run_id=run_id,
            question_id=question_id,
            qa_set_id=question.qa_set_id,
            text=question.text,
            tags=list(question.tags),
            answerable=question.answerable,
            gold_documents=[
                UncoveredDocumentRead(document_id=document_id, filename=filename)
                for document_id, filename in gold
            ],
            variants=variants,
        )

    async def _evidence(
        self,
        question_id: uuid.UUID,
        configuration_id: uuid.UUID,
        *,
        retrieved: set[uuid.UUID | None],
    ) -> tuple[str, list[GoldChunkRead]]:
        """Status of a question's evidence under a configuration, and its chunks if confirmed."""
        evidence = EvidenceRepository(self.session)
        link = await evidence.get(question_id, configuration_id)
        if link is None:
            return NOT_REVIEWED, []
        if link.status != EvidenceLinkStatus.CONFIRMED:
            return link.status.value, []
        return link.status.value, [
            GoldChunkRead(
                chunk_id=chunk.id,
                document_id=document_id,
                filename=filename,
                ordinal=chunk.ordinal,
                page=_page(chunk),
                text=chunk.text,
                relevance=item.relevance,
                graded_relevance=item.graded_relevance,
                retrieved=chunk.id in retrieved,
            )
            for item, chunk, document_id, filename in await evidence.chunks_of_link(
                link.id
            )
        ]
