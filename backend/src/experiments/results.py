from __future__ import annotations

import csv
import io
import uuid
from collections.abc import Sequence

from sqlalchemy import Row
from sqlalchemy.ext.asyncio import AsyncSession

from src.corpora.repository import CorpusSnapshotRepository
from src.experiments.evaluation import CHUNK_GOLD_KEY
from src.experiments.exceptions import QuestionNotInRunError
from src.experiments.metrics import (
    CHUNK_FIRST_RELEVANT_RANK,
    FIRST_RELEVANT_RANK,
    metric_specs,
)
from src.experiments.models import Execution
from src.experiments.repository import (
    EvaluationRepository,
    ExecutionRepository,
)
from src.experiments.schemas import (
    CallDetailRead,
    ChunkGoldRead,
    ComparisonRead,
    ComparisonSkippedRead,
    ComparisonVariantRead,
    EvidenceCountsRead,
    ExecutionDetailRead,
    GoldChunkRead,
    HitDetailRead,
    HitOccurrenceRead,
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
from src.infrastructure.database.enums import (
    EvidenceLinkStatus,
    ExecutionStatus,
    ExperimentType,
    RelevanceGrade,
)
from src.infrastructure.observability import trace_url
from src.pipelines.service import ChunkingConfigurationService, ProfileService
from src.qa_sets.exceptions import QASetSnapshotNotFoundError
from src.qa_sets.repository import (
    EvidenceRepository,
    QASetSnapshotRepository,
    QuestionRepository,
)
from src.qa_sets.service import NOT_REVIEWED
from src.qa_sets.utils import recall_ceiling
from src.settings import get_settings

CSV_COLUMNS = (
    "chunking_configuration_id",
    "variant",
    "is_baseline",
    "family",
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


ANSWER_CSV_COLUMNS = (
    "question_id",
    "question",
    "tags",
    "answerable",
    "expected_answer",
    "variant",
    "is_baseline",
    "repetition",
    "status",
    "refused",
    "answer",
    "cited_chunks",
    "model",
    "input_tokens",
    "output_tokens",
    "total_ms",
    "error",
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
        # The wording comes from the code and not from the stored definition: seeding
        # leaves existing rows untouched, so a clearer description would never reach them.
        descriptions = {spec.key: spec.description for spec in metric_specs()}
        aggregates = await self.evaluations.aggregates_for_run(
            run_id, slice_key=slice_key, slice_value=slice_value
        )
        per_variant: dict[uuid.UUID, list[MetricResultRead]] = {}
        for aggregate in aggregates:
            definition = by_id[aggregate.metric_definition_id]
            per_variant.setdefault(aggregate.variant_id, []).append(
                MetricResultRead(
                    key=definition.key,
                    level=definition.level,
                    family=definition.family,
                    direction=definition.direction,
                    aggregation=definition.aggregation,
                    description=descriptions.get(definition.key)
                    or definition.description
                    or "",
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
            experiment_type=experiment.type,
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
            groups=list(groups.values()),
        )

    async def comparison(
        self, qa_set_snapshot_id: uuid.UUID, experiment_type: ExperimentType
    ) -> ComparisonRead:
        """The variants of every experiment of one type on a QA set snapshot, flattened.

        Each experiment contributes the metrics of its latest finished run; one without a
        finished run is reported as skipped rather than silently missing. The chunking
        configuration stays on each variant as information: every metric is a ratio or an
        amount, so they compare across configurations, and the question count behind each
        value is what shows when two values do not rest on the same questions.

        Raises:
            QASetSnapshotNotFoundError: If the QA set snapshot does not exist.
        """
        snapshot = await self.qa_snapshots.get_by_id(qa_set_snapshot_id)
        if snapshot is None:
            raise QASetSnapshotNotFoundError(qa_set_snapshot_id)
        variants: list[ComparisonVariantRead] = []
        skipped: list[ComparisonSkippedRead] = []
        experiments = await self.experiments.experiments.list_for_comparison(
            qa_set_snapshot_id, experiment_type
        )
        for experiment in experiments:
            runs = await self.runs.runs.list_by_experiment(experiment.id)
            run = next(
                (item for item in runs if item.status == ExecutionStatus.SUCCEEDED),
                None,
            )
            if run is None:
                skipped.append(
                    ComparisonSkippedRead(
                        experiment_id=experiment.id,
                        experiment_name=experiment.name,
                        reason="no finished run",
                    )
                )
                continue
            results = await self.results(experiment.id, run.id)
            for group in results.groups:
                for variant in group.variants:
                    variants.append(
                        ComparisonVariantRead(
                            **variant.model_dump(),
                            experiment_id=experiment.id,
                            experiment_name=experiment.name,
                            run_id=run.id,
                            corpus_snapshot=results.corpus_snapshot,
                            chunking_configuration_id=group.chunking_configuration_id,
                            chunking_configuration_name=group.chunking_configuration_name,
                            recall_ceiling=group.recall_ceiling,
                        )
                    )
        return ComparisonRead(
            qa_set_snapshot=SnapshotDeclaredRead(
                id=snapshot.id,
                label=snapshot.label,
                question_count=snapshot.question_count,
            ),
            experiment_type=experiment_type,
            variants=variants,
            skipped=skipped,
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
                            metric.family.value,
                            metric.level.value if metric.level else "",
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

    async def answers_csv(self, experiment_id: uuid.UUID, run_id: uuid.UUID) -> str:
        """Every answer of a run as CSV: one row per question, variant and repetition.

        Rows follow the question order of the snapshot, then the variants, then the
        repetitions, so the answers of one question sit together next to the expected one.
        A retrieval run has the rows with the answer columns empty.

        Raises:
            RunNotFoundError: If the run does not exist or belongs to another experiment.
        """
        await self.runs.get(run_id, experiment_id)
        experiment = await self.experiments.get(experiment_id)
        question_ids = await self.qa_snapshots.question_ids(
            experiment.qa_set_snapshot_id
        )
        questions = {
            question.id: question
            for question in await self.questions.list_by_ids(question_ids)
        }
        expected = await self.questions.answers_by_question(question_ids)
        views = await self.experiments.variant_views(experiment_id)
        variant_rank = {view.variant.id: index for index, view in enumerate(views)}
        variants = {view.variant.id: view.variant for view in views}
        question_rank = {
            question_id: index for index, question_id in enumerate(question_ids)
        }
        executions = sorted(
            await self.executions.list_by_run(run_id),
            key=lambda item: (
                question_rank.get(item.question_id, len(question_rank)),
                variant_rank.get(item.variant_id, len(variant_rank)),
                item.repetition,
            ),
        )

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(ANSWER_CSV_COLUMNS)
        for execution in executions:
            question = questions.get(execution.question_id)
            variant = variants[execution.variant_id]
            answers = expected.get(execution.question_id) or []
            usage = execution.usage or {}
            timings = execution.timings or {}
            writer.writerow(
                [
                    execution.question_id,
                    question.text if question else "",
                    "|".join(question.tags) if question else "",
                    question.answerable if question else "",
                    answers[0].text if answers else "",
                    variant.name,
                    variant.is_baseline,
                    execution.repetition,
                    execution.status.value,
                    "" if execution.refused is None else execution.refused,
                    execution.answer_text or "",
                    ""
                    if execution.cited_chunk_ids is None
                    else len(execution.cited_chunk_ids),
                    usage.get("model", ""),
                    usage.get("input_tokens", ""),
                    usage.get("output_tokens", ""),
                    timings.get("total_ms", ""),
                    execution.error or "",
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
        open, and the drill-down shows every repetition. In a Q&A run it carries the answer
        and whether it refused, and each question its primary expected answer, so the
        answers can be read side by side without opening every question.
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
        expected = await self.questions.answers_by_question(page_ids)
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
                    answer_text=execution.answer_text,
                    refused=execution.refused,
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
                    expected_answer=(
                        expected[question_id][0].text
                        if expected.get(question_id)
                        else None
                    ),
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
        """What each variant retrieved, and answered, for a question, call by call.

        In a Q&A run each execution carries its answer, whether it refused and what it
        used, and the question its primary expected answer. Each execution lists its
        calls, with the query and how many chunks each brought
        that no earlier call had, and its distinct chunks, each with every call and rank it
        was returned at: a chunk retrieved twice is shown twice-retrieved, not hidden in
        the set. Chunks the answer system cited without retrieving them come last. Each
        chunk says whether its document is gold and whether the chunk itself is an evidence
        chunk under the variant's configuration, as of the last scoring. Each variant also
        lists the evidence chunks of that configuration as they are now, the ones it did
        not retrieve included, which is what the annotation page links to.

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
        expected = (await self.questions.answers_by_question([question_id])).get(
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
        rows = await self.executions.hit_details(
            [execution.id for execution in executions]
        )
        hits = await self._distinct_hits(executions, rows)
        calls = await self._calls(executions, rows)
        gold_ids = {document_id for document_id, _ in gold}
        langfuse_host = get_settings().langfuse_host

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
                    if hit.retrieved
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
                            answer_text=execution.answer_text,
                            refused=execution.refused,
                            usage=execution.usage,
                            langfuse_trace_url=trace_url(
                                execution.langfuse_trace_id, langfuse_host
                            ),
                            calls=calls.get(execution.id, []),
                            citations_declared=execution.cited_chunk_ids is not None,
                            hits=[
                                _graded(
                                    hit,
                                    grades,
                                    status,
                                    gold_ids if question.answerable else set(),
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
            expected_answer=expected[0].text if expected else None,
            gold_documents=[
                UncoveredDocumentRead(document_id=document_id, filename=filename)
                for document_id, filename in gold
            ],
            variants=variants,
        )

    async def _distinct_hits(
        self, executions: Sequence[Execution], rows: Sequence[Row]
    ) -> dict[uuid.UUID, list[HitDetailRead]]:
        """Each execution's distinct chunks with their occurrences, then those only cited."""
        hits: dict[uuid.UUID, dict[uuid.UUID | int, HitDetailRead]] = {}
        for index, (
            execution_id,
            call_index,
            hit,
            chunk,
            document_id,
            filename,
        ) in enumerate(rows):
            own = hits.setdefault(execution_id, {})
            # A hit whose chunk is gone cannot be matched to another: it stands alone.
            key = hit.chunk_id if hit.chunk_id is not None else index
            if key not in own:
                own[key] = HitDetailRead(
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
            own[key].occurrences.append(
                HitOccurrenceRead(call_index=call_index, rank=hit.rank, score=hit.score)
            )

        cited_only = {
            chunk_id
            for execution in executions
            for chunk_id in execution.cited_chunk_ids or []
            if chunk_id not in hits.get(execution.id, {})
        }
        details = {
            chunk.id: (chunk, document_id, filename)
            for chunk, document_id, filename in await self.executions.chunk_details(
                list(cited_only)
            )
        }
        result: dict[uuid.UUID, list[HitDetailRead]] = {}
        for execution in executions:
            own = hits.get(execution.id, {})
            cited = (
                set(execution.cited_chunk_ids)
                if execution.cited_chunk_ids is not None
                else None
            )
            items = [
                item.model_copy(
                    update={
                        "cited": item.chunk_id in cited if cited is not None else None
                    }
                )
                for item in own.values()
            ]
            for chunk_id in dict.fromkeys(execution.cited_chunk_ids or []):
                if chunk_id in own:
                    continue
                chunk, document_id, filename = details.get(chunk_id, (None, None, None))
                items.append(
                    HitDetailRead(
                        rank=None,
                        score=None,
                        chunk_id=chunk_id,
                        document_id=document_id,
                        filename=filename,
                        ordinal=chunk.ordinal if chunk is not None else None,
                        page=_page(chunk),
                        text=chunk.text if chunk is not None else None,
                        relevant_document=None,
                        retrieved=False,
                        cited=True,
                    )
                )
            result[execution.id] = items
        return result

    async def _calls(
        self, executions: Sequence[Execution], rows: Sequence[Row]
    ) -> dict[uuid.UUID, list[CallDetailRead]]:
        """Each execution's calls with their hit count and the chunks new to each."""
        per_call: dict[tuple[uuid.UUID, int], list[uuid.UUID | None]] = {}
        for execution_id, call_index, hit, *_ in rows:
            per_call.setdefault((execution_id, call_index), []).append(hit.chunk_id)
        result: dict[uuid.UUID, list[CallDetailRead]] = {}
        seen: dict[uuid.UUID, set[uuid.UUID]] = {}
        for call in await self.executions.calls_of_executions(
            [execution.id for execution in executions]
        ):
            chunks = per_call.get((call.execution_id, call.call_index), [])
            before = seen.setdefault(call.execution_id, set())
            new = {chunk_id for chunk_id in chunks if chunk_id not in before}
            before.update(chunk_id for chunk_id in chunks if chunk_id is not None)
            result.setdefault(call.execution_id, []).append(
                CallDetailRead(
                    call_index=call.call_index,
                    query_text=call.query_text,
                    hit_count=len(chunks),
                    new_chunk_count=len(new)
                    + sum(1 for chunk_id in chunks if chunk_id is None),
                )
            )
        return result

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


def _graded(
    hit: HitDetailRead,
    grades: dict[uuid.UUID, RelevanceGrade],
    evidence_status: str,
    gold_documents: set[uuid.UUID],
) -> HitDetailRead:
    """A chunk with its evidence grade; a cited-only chunk also gets its relevance flags.

    The flags of a retrieved chunk are those written by the last scoring; a chunk that was
    only cited has no hit to carry them, so they are read from the gold as it is now.
    """
    update: dict = {"relevance": grades.get(hit.chunk_id)}
    if not hit.retrieved:
        update["relevant_document"] = (
            hit.document_id in gold_documents if gold_documents else None
        )
        update["relevant_chunk"] = (
            hit.chunk_id in grades
            if evidence_status == EvidenceLinkStatus.CONFIRMED.value
            else None
        )
    return hit.model_copy(update=update)
