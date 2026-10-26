from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.artifacts.models import Chunk, ChunkResult
from src.corpora.models import Corpus, CorpusSnapshot, CorpusSnapshotDocument
from src.documents.models import Document
from src.experiments.models import (
    Evaluation,
    Execution,
    Experiment,
    MetricAggregate,
    MetricDefinition,
    RetrievalCall,
    RetrievalHit,
    Run,
    Variant,
)
from src.infrastructure.database.enums import ExecutionStatus, RetrievalStage
from src.qa_sets.models import (
    GoldDocument,
    QASet,
    QASetSnapshot,
    QASnapshotQuestion,
    Question,
)

# Rows per INSERT: asyncpg caps a statement at 32767 bind parameters, and an execution row
# binds four, an aggregate thirteen.
_EXECUTION_BATCH = 1000
_AGGREGATE_BATCH = 1000


@dataclasses.dataclass(frozen=True)
class UncoveredQuestion:
    """A question whose gold documents are not all in the corpus snapshot."""

    question_id: uuid.UUID
    text: str
    missing_documents: list[tuple[uuid.UUID, str]]


@dataclasses.dataclass(frozen=True)
class SnapshotOrigin:
    """The corpus and the QA set an experiment's two snapshots were frozen from."""

    corpus_id: uuid.UUID
    corpus_name: str
    corpus_snapshot_label: str
    qa_set_id: uuid.UUID
    qa_set_name: str
    qa_set_snapshot_label: str


class ExperimentRepository:
    """Data access for `experiments` and `variants`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, experiment: Experiment) -> Experiment:
        self.session.add(experiment)
        return experiment

    def add_variant(self, variant: Variant) -> Variant:
        self.session.add(variant)
        return variant

    async def get_by_id(self, experiment_id: uuid.UUID) -> Experiment | None:
        return await self.session.get(Experiment, experiment_id)

    async def get_variant(self, variant_id: uuid.UUID) -> Variant | None:
        return await self.session.get(Variant, variant_id)

    async def list(self, *, limit: int = 50, offset: int = 0) -> Sequence[Experiment]:
        stmt = (
            select(Experiment)
            .order_by(Experiment.created_at.desc(), Experiment.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return (await self.session.scalars(stmt)).all()

    async def count(self) -> int:
        return (
            await self.session.scalar(select(func.count()).select_from(Experiment)) or 0
        )

    async def list_variants(self, experiment_id: uuid.UUID) -> Sequence[Variant]:
        stmt = (
            select(Variant)
            .where(Variant.experiment_id == experiment_id)
            .order_by(Variant.created_at, Variant.name, Variant.id)
        )
        return (await self.session.scalars(stmt)).all()

    async def variant_counts(
        self, experiment_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        if not experiment_ids:
            return {}
        stmt = (
            select(Variant.experiment_id, func.count())
            .where(Variant.experiment_id.in_(experiment_ids))
            .group_by(Variant.experiment_id)
        )
        return {key: count for key, count in (await self.session.execute(stmt)).all()}

    async def snapshot_origins(
        self, experiment_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, SnapshotOrigin]:
        """The corpus and QA set behind each experiment, keyed by experiment id."""
        if not experiment_ids:
            return {}
        stmt = (
            select(
                Experiment.id,
                Corpus.id,
                Corpus.name,
                CorpusSnapshot.label,
                QASet.id,
                QASet.name,
                QASetSnapshot.label,
            )
            .join(CorpusSnapshot, CorpusSnapshot.id == Experiment.corpus_snapshot_id)
            .join(Corpus, Corpus.id == CorpusSnapshot.corpus_id)
            .join(QASetSnapshot, QASetSnapshot.id == Experiment.qa_set_snapshot_id)
            .join(QASet, QASet.id == QASetSnapshot.qa_set_id)
            .where(Experiment.id.in_(experiment_ids))
        )
        return {
            row[0]: SnapshotOrigin(*row[1:])
            for row in (await self.session.execute(stmt)).all()
        }

    async def uncovered_questions(
        self, qa_set_snapshot_id: uuid.UUID, corpus_snapshot_id: uuid.UUID
    ) -> list[UncoveredQuestion]:
        """Answerable questions of a QA snapshot with a gold document outside a corpus snapshot.

        Unanswerable questions are not listed: they are left out of the metrics anyway, and
        their gold documents, if any, are not what a retriever is asked to find.
        """
        stmt = (
            select(Question.id, Question.text, Document.id, Document.filename)
            .join(QASnapshotQuestion, QASnapshotQuestion.question_id == Question.id)
            .join(GoldDocument, GoldDocument.question_id == Question.id)
            .join(Document, Document.id == GoldDocument.document_id)
            .outerjoin(
                CorpusSnapshotDocument,
                (CorpusSnapshotDocument.document_id == GoldDocument.document_id)
                & (CorpusSnapshotDocument.snapshot_id == corpus_snapshot_id),
            )
            .where(
                QASnapshotQuestion.snapshot_id == qa_set_snapshot_id,
                Question.answerable.is_(True),
                CorpusSnapshotDocument.document_id.is_(None),
            )
            .order_by(Question.text, Question.id, Document.filename)
        )
        grouped: dict[uuid.UUID, UncoveredQuestion] = {}
        for question_id, text, document_id, filename in (
            await self.session.execute(stmt)
        ).all():
            entry = grouped.setdefault(
                question_id, UncoveredQuestion(question_id, text, [])
            )
            entry.missing_documents.append((document_id, filename))
        return list(grouped.values())

    async def gold_outside_snapshot(
        self, question_id: uuid.UUID, corpus_snapshot_id: uuid.UUID
    ) -> bool:
        """Whether any gold document of a question is missing from a corpus snapshot."""
        stmt = (
            select(func.count())
            .select_from(GoldDocument)
            .outerjoin(
                CorpusSnapshotDocument,
                (CorpusSnapshotDocument.document_id == GoldDocument.document_id)
                & (CorpusSnapshotDocument.snapshot_id == corpus_snapshot_id),
            )
            .where(
                GoldDocument.question_id == question_id,
                CorpusSnapshotDocument.document_id.is_(None),
            )
        )
        return (await self.session.scalar(stmt) or 0) > 0

    async def gold_document_ids(self, question_id: uuid.UUID) -> set[uuid.UUID]:
        stmt = select(GoldDocument.document_id).where(
            GoldDocument.question_id == question_id
        )
        return set((await self.session.scalars(stmt)).all())


class RunRepository:
    """Data access for `runs`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, run: Run) -> Run:
        self.session.add(run)
        return run

    async def get_by_id(self, run_id: uuid.UUID) -> Run | None:
        return await self.session.get(Run, run_id)

    async def list_by_experiment(self, experiment_id: uuid.UUID) -> Sequence[Run]:
        stmt = (
            select(Run)
            .where(Run.experiment_id == experiment_id)
            .order_by(Run.created_at.desc(), Run.id.desc())
        )
        return (await self.session.scalars(stmt)).all()


class ExecutionRepository:
    """Data access for `executions` and their tracked retrieval."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_many(self, rows: Sequence[dict]) -> None:
        """Insert executions in batches; a row already present for its key is left alone."""
        for start in range(0, len(rows), _EXECUTION_BATCH):
            batch = rows[start : start + _EXECUTION_BATCH]
            await self.session.execute(
                pg_insert(Execution).values(batch).on_conflict_do_nothing()
            )

    async def get_by_id(self, execution_id: uuid.UUID) -> Execution | None:
        return await self.session.get(Execution, execution_id)

    async def count_by_status(
        self, run_id: uuid.UUID, *, variant_id: uuid.UUID | None = None
    ) -> dict[ExecutionStatus, int]:
        stmt = select(Execution.status, func.count()).where(Execution.run_id == run_id)
        if variant_id is not None:
            stmt = stmt.where(Execution.variant_id == variant_id)
        stmt = stmt.group_by(Execution.status)
        return {
            status: count for status, count in (await self.session.execute(stmt)).all()
        }

    async def reset_running(self, run_id: uuid.UUID) -> None:
        """Put executions an interrupted attempt left `running` back to `pending`."""
        await self.session.execute(
            update(Execution)
            .where(
                Execution.run_id == run_id, Execution.status == ExecutionStatus.RUNNING
            )
            .values(status=ExecutionStatus.PENDING)
        )

    async def unfinished_ids(
        self,
        run_id: uuid.UUID,
        variant_id: uuid.UUID,
        *,
        after_id: uuid.UUID | None,
        limit: int,
    ) -> list[uuid.UUID]:
        """One page of the executions of a variant that did not succeed, by id.

        Keyed on the last id seen and not on an offset: executions leave this set as they
        succeed, so an offset would skip the ones that move into its place.
        """
        stmt = select(Execution.id).where(
            Execution.run_id == run_id,
            Execution.variant_id == variant_id,
            Execution.status != ExecutionStatus.SUCCEEDED,
        )
        if after_id is not None:
            stmt = stmt.where(Execution.id > after_id)
        stmt = stmt.order_by(Execution.id).limit(limit)
        return list((await self.session.scalars(stmt)).all())

    async def list_by_run(self, run_id: uuid.UUID) -> Sequence[Execution]:
        stmt = select(Execution).where(Execution.run_id == run_id)
        return (await self.session.scalars(stmt)).all()

    async def list_for_question(
        self, run_id: uuid.UUID, question_id: uuid.UUID
    ) -> Sequence[Execution]:
        stmt = (
            select(Execution)
            .where(Execution.run_id == run_id, Execution.question_id == question_id)
            .order_by(Execution.variant_id, Execution.repetition)
        )
        return (await self.session.scalars(stmt)).all()

    async def question_row_executions(
        self, run_id: uuid.UUID, question_ids: Sequence[uuid.UUID]
    ) -> Sequence[Execution]:
        """First-repetition executions of some questions, for the question table."""
        stmt = select(Execution).where(
            Execution.run_id == run_id,
            Execution.question_id.in_(question_ids),
            Execution.repetition == 1,
        )
        return (await self.session.scalars(stmt)).all()

    # -- tracked retrieval ---------------------------------------------------------------

    async def next_call_index(self, execution_id: uuid.UUID) -> int:
        stmt = select(func.coalesce(func.max(RetrievalCall.call_index), 0)).where(
            RetrievalCall.execution_id == execution_id
        )
        return (await self.session.scalar(stmt) or 0) + 1

    def add_call(self, call: RetrievalCall) -> RetrievalCall:
        self.session.add(call)
        return call

    async def add_hits(self, hits: Sequence[RetrievalHit]) -> None:
        self.session.add_all(hits)
        await self.session.flush()

    async def record_call(
        self, execution_id: uuid.UUID, query_text: str, hits: Sequence[dict]
    ) -> RetrievalCall:
        """Record one retrieval call of an execution with the hits it returned.

        Args:
            execution_id: Execution the call belongs to.
            query_text: Query as actually sent, which an agent may have rewritten.
            hits: One mapping per hit with `chunk_id`, `rank`, `score` and `stage`.
        """
        call = self.add_call(
            RetrievalCall(
                execution_id=execution_id,
                call_index=await self.next_call_index(execution_id),
                query_text=query_text,
            )
        )
        await self.session.flush()
        await self.add_hits(
            [RetrievalHit(retrieval_call_id=call.id, **hit) for hit in hits]
        )
        return call

    async def clear_calls(self, execution_id: uuid.UUID) -> None:
        """Forget what an earlier attempt of an execution retrieved."""
        await self.session.execute(
            delete(RetrievalCall).where(RetrievalCall.execution_id == execution_id)
        )

    async def hits_of_execution(
        self, execution_id: uuid.UUID
    ) -> list[tuple[RetrievalHit, uuid.UUID | None]]:
        """Final hits of an execution with their document, in call then rank order."""
        stmt = (
            select(RetrievalHit, ChunkResult.document_id)
            .join(RetrievalCall, RetrievalCall.id == RetrievalHit.retrieval_call_id)
            .outerjoin(Chunk, Chunk.id == RetrievalHit.chunk_id)
            .outerjoin(ChunkResult, ChunkResult.id == Chunk.chunk_result_id)
            .where(
                RetrievalCall.execution_id == execution_id,
                RetrievalHit.stage == RetrievalStage.FINAL,
            )
            .order_by(RetrievalCall.call_index, RetrievalHit.rank)
        )
        return [
            (hit, document_id)
            for hit, document_id in (await self.session.execute(stmt)).all()
        ]

    async def hit_details(self, execution_ids: Sequence[uuid.UUID]):
        """Hits of some executions with chunk, document and filename, for the drill-down."""
        stmt = (
            select(
                RetrievalCall.execution_id,
                RetrievalHit,
                Chunk,
                ChunkResult.document_id,
                Document.filename,
            )
            .join(RetrievalCall, RetrievalCall.id == RetrievalHit.retrieval_call_id)
            .outerjoin(Chunk, Chunk.id == RetrievalHit.chunk_id)
            .outerjoin(ChunkResult, ChunkResult.id == Chunk.chunk_result_id)
            .outerjoin(Document, Document.id == ChunkResult.document_id)
            .where(
                RetrievalCall.execution_id.in_(execution_ids),
                RetrievalHit.stage == RetrievalStage.FINAL,
            )
            .order_by(
                RetrievalCall.execution_id, RetrievalCall.call_index, RetrievalHit.rank
            )
        )
        return (await self.session.execute(stmt)).all()


@dataclasses.dataclass(frozen=True)
class EvaluationRow:
    """An evaluation with the context an aggregate groups it by."""

    variant_id: uuid.UUID
    metric_definition_id: uuid.UUID
    score: float | None
    excluded: bool
    tags: list[str]


class EvaluationRepository:
    """Data access for `evaluations` and `metric_aggregates`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def replace_for_execution(
        self, execution_id: uuid.UUID, evaluator_id: uuid.UUID, rows: Sequence[dict]
    ) -> None:
        """Write an execution's evaluations, replacing those of an earlier attempt."""
        await self.session.execute(
            delete(Evaluation).where(
                Evaluation.execution_id == execution_id,
                Evaluation.evaluator_id == evaluator_id,
            )
        )
        if rows:
            await self.session.execute(pg_insert(Evaluation).values(list(rows)))

    async def rows_for_run(self, run_id: uuid.UUID) -> list[EvaluationRow]:
        stmt = (
            select(
                Execution.variant_id,
                Evaluation.metric_definition_id,
                Evaluation.score,
                Evaluation.excluded,
                Question.tags,
            )
            .join(Execution, Execution.id == Evaluation.execution_id)
            .join(Question, Question.id == Execution.question_id)
            .where(Execution.run_id == run_id)
        )
        return [
            EvaluationRow(variant_id, metric_id, score, excluded, list(tags))
            for variant_id, metric_id, score, excluded, tags in (
                await self.session.execute(stmt)
            ).all()
        ]

    async def evaluations_of_executions(
        self, execution_ids: Sequence[uuid.UUID]
    ) -> Sequence[Evaluation]:
        if not execution_ids:
            return []
        stmt = select(Evaluation).where(Evaluation.execution_id.in_(execution_ids))
        return (await self.session.scalars(stmt)).all()

    async def metric_definitions(self) -> dict[str, MetricDefinition]:
        """Every metric definition by key."""
        return {
            definition.key: definition
            for definition in await self.session.scalars(select(MetricDefinition))
        }

    async def replace_aggregates(self, run_id: uuid.UUID, rows: Sequence[dict]) -> None:
        await self.session.execute(
            delete(MetricAggregate).where(MetricAggregate.run_id == run_id)
        )
        for start in range(0, len(rows), _AGGREGATE_BATCH):
            await self.session.execute(
                pg_insert(MetricAggregate).values(
                    list(rows[start : start + _AGGREGATE_BATCH])
                )
            )

    async def aggregates_for_run(
        self, run_id: uuid.UUID, *, slice_key: str, slice_value: str
    ) -> Sequence[MetricAggregate]:
        stmt = select(MetricAggregate).where(
            MetricAggregate.run_id == run_id,
            MetricAggregate.slice_key == slice_key,
            MetricAggregate.slice_value == slice_value,
        )
        return (await self.session.scalars(stmt)).all()
