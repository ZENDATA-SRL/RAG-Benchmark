from __future__ import annotations

import dataclasses
import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import UnsupportedOperationError
from src.corpora.exceptions import CorpusSnapshotNotFoundError
from src.corpora.repository import CorpusSnapshotRepository
from src.experiments.evaluation import EvaluationService
from src.experiments.exceptions import (
    ExperimentNotFoundError,
    GoldCoverageChoiceRequiredError,
    MultipleBaselinesError,
    RunInProgressError,
    RunNotCancellableError,
    RunNotFoundError,
    RunNotResumableError,
    VariantsOutsideSnapshotError,
)
from src.experiments.models import Experiment, Run, Variant
from src.experiments.repository import (
    ExecutionRepository,
    ExperimentRepository,
    RunRepository,
    SnapshotOrigin,
    UncoveredQuestion,
)
from src.indexes.models import IndexBuild
from src.indexes.service import IndexBuildService
from src.infrastructure.database.enums import (
    ArtifactStatus,
    ExecutionStatus,
    ExperimentType,
)
from src.infrastructure.temporal import WorkflowClient
from src.infrastructure.temporal.workflow_ids import (
    EXPERIMENTS_TASK_QUEUE,
    RUN_EXPERIMENT_WORKFLOW,
    run_experiment_workflow_id,
)
from src.pipelines.models import RetrievalProfile
from src.pipelines.service import ProfileService
from src.qa_sets.exceptions import QASetSnapshotNotFoundError
from src.qa_sets.repository import QASetSnapshotRepository
from src.retrieval.exceptions import IndexBuildNotReadyError

# Queries per run processed at once: the query embeddings are rate limited, so the default
# is modest and a run can lower or raise it.
DEFAULT_RUN_CONCURRENCY = 5

CANCELLED_REASON = "cancelled"
EXCLUDE_UNCOVERED = "exclude"


@dataclasses.dataclass(frozen=True)
class VariantInput:
    """A variant as requested: an index build searched under a retrieval profile."""

    name: str
    index_build_id: uuid.UUID
    retrieval_profile_id: uuid.UUID
    is_baseline: bool = False


@dataclasses.dataclass(frozen=True)
class VariantView:
    """A variant with the index build and retrieval profile it points at."""

    variant: Variant
    index_build: IndexBuild
    retrieval_profile: RetrievalProfile


@dataclasses.dataclass(frozen=True)
class CoverageReport:
    """How many questions of a QA snapshot have their gold documents in a corpus snapshot."""

    question_count: int
    uncovered: list[UncoveredQuestion]


@dataclasses.dataclass(frozen=True)
class ExperimentView:
    """An experiment with its variants, runs and the coverage of its gold documents."""

    experiment: Experiment
    variants: list[VariantView]
    runs: Sequence[Run]
    coverage: CoverageReport
    origin: SnapshotOrigin | None


@dataclasses.dataclass(frozen=True)
class RunLaunch:
    """A launched run and whether this request is what started its workflow."""

    run: Run
    started: bool


class ExperimentService:
    """Creation of experiments and the guards that keep their comparisons meaningful."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.experiments = ExperimentRepository(session)
        self.runs = RunRepository(session)
        self.corpus_snapshots = CorpusSnapshotRepository(session)
        self.qa_snapshots = QASetSnapshotRepository(session)
        self.builds = IndexBuildService(session)
        self.profiles = ProfileService(session)

    async def coverage(
        self, corpus_snapshot_id: uuid.UUID, qa_set_snapshot_id: uuid.UUID
    ) -> CoverageReport:
        """Check which questions have gold documents outside a corpus snapshot.

        Raises:
            CorpusSnapshotNotFoundError: If the corpus snapshot does not exist.
            QASetSnapshotNotFoundError: If the QA set snapshot does not exist.
        """
        if await self.corpus_snapshots.get_by_id(corpus_snapshot_id) is None:
            raise CorpusSnapshotNotFoundError(corpus_snapshot_id)
        qa_snapshot = await self.qa_snapshots.get_by_id(qa_set_snapshot_id)
        if qa_snapshot is None:
            raise QASetSnapshotNotFoundError(qa_set_snapshot_id)
        return CoverageReport(
            question_count=qa_snapshot.question_count,
            uncovered=await self.experiments.uncovered_questions(
                qa_set_snapshot_id, corpus_snapshot_id
            ),
        )

    async def create(
        self,
        *,
        name: str,
        type: ExperimentType,
        corpus_snapshot_id: uuid.UUID,
        qa_set_snapshot_id: uuid.UUID,
        repetitions: int,
        variants: Sequence[VariantInput],
        uncovered_policy: str | None = None,
    ) -> Experiment:
        """Create an experiment after checking its search space and its gold coverage.

        Two guards run before anything is written. Every variant's index build must have
        been built on the experiment's corpus snapshot: otherwise one variant would search
        50 documents and another 200 and the comparison would mean nothing. And every
        question's gold documents must be in that snapshot, or the caller must say to
        exclude the questions that are not covered: counting them as retrieval failures,
        which is what doing nothing would do, would blame the retriever for an answer that
        was never in the search space.

        At most one variant is the baseline; when none is marked, the first one is.

        Raises:
            UnsupportedOperationError: If the type is not `retrieval`.
            CorpusSnapshotNotFoundError: If the corpus snapshot does not exist.
            QASetSnapshotNotFoundError: If the QA set snapshot does not exist.
            IndexBuildNotFoundError: If a variant's index build does not exist.
            ProfileNotFoundError: If a variant's retrieval profile does not exist.
            MultipleBaselinesError: If more than one variant is the baseline.
            VariantsOutsideSnapshotError: If a variant's index is on another snapshot.
            GoldCoverageChoiceRequiredError: If some questions are not covered and no
                policy was chosen.
        """
        if type is not ExperimentType.RETRIEVAL:
            raise UnsupportedOperationError(
                f"experiments of type {type.value!r} are not supported yet"
            )
        coverage = await self.coverage(corpus_snapshot_id, qa_set_snapshot_id)

        baselines = [variant.name for variant in variants if variant.is_baseline]
        if len(baselines) > 1:
            raise MultipleBaselinesError(baselines)

        outside = []
        for variant in variants:
            build = await self.builds.get(variant.index_build_id)
            await self.profiles.get_retrieval_profile(variant.retrieval_profile_id)
            if build.corpus_snapshot_id != corpus_snapshot_id:
                outside.append(
                    {
                        "name": variant.name,
                        "index_build_id": str(build.id),
                        "index_build_snapshot_id": str(build.corpus_snapshot_id),
                    }
                )
        if outside:
            raise VariantsOutsideSnapshotError(corpus_snapshot_id, outside)

        if coverage.uncovered and uncovered_policy != EXCLUDE_UNCOVERED:
            raise GoldCoverageChoiceRequiredError(
                [
                    {
                        "question_id": str(question.question_id),
                        "text": question.text,
                        "missing_documents": [
                            {"document_id": str(document_id), "filename": filename}
                            for document_id, filename in question.missing_documents
                        ],
                    }
                    for question in coverage.uncovered
                ]
            )

        experiment = self.experiments.add(
            Experiment(
                name=name,
                type=type,
                corpus_snapshot_id=corpus_snapshot_id,
                qa_set_snapshot_id=qa_set_snapshot_id,
                repetitions=repetitions,
                uncovered_policy=uncovered_policy if coverage.uncovered else None,
            )
        )
        await self.session.flush()
        for index, variant in enumerate(variants):
            self.experiments.add_variant(
                Variant(
                    experiment_id=experiment.id,
                    name=variant.name,
                    index_build_id=variant.index_build_id,
                    retrieval_profile_id=variant.retrieval_profile_id,
                    is_baseline=variant.is_baseline or (not baselines and index == 0),
                )
            )
        await self.session.flush()
        await self.session.refresh(experiment)
        return experiment

    async def get(self, experiment_id: uuid.UUID) -> Experiment:
        """Return an experiment.

        Raises:
            ExperimentNotFoundError: If it does not exist.
        """
        experiment = await self.experiments.get_by_id(experiment_id)
        if experiment is None:
            raise ExperimentNotFoundError(experiment_id)
        return experiment

    async def detail(self, experiment_id: uuid.UUID) -> ExperimentView:
        """An experiment with its variants, its runs and the coverage of its gold documents.

        Raises:
            ExperimentNotFoundError: If it does not exist.
        """
        experiment = await self.get(experiment_id)
        return ExperimentView(
            experiment=experiment,
            variants=await self.variant_views(experiment_id),
            runs=await self.runs.list_by_experiment(experiment_id),
            coverage=await self.coverage(
                experiment.corpus_snapshot_id, experiment.qa_set_snapshot_id
            ),
            origin=(await self.experiments.snapshot_origins([experiment_id])).get(
                experiment_id
            ),
        )

    async def variant_views(self, experiment_id: uuid.UUID) -> list[VariantView]:
        views = []
        for variant in await self.experiments.list_variants(experiment_id):
            views.append(
                VariantView(
                    variant=variant,
                    index_build=await self.builds.get(variant.index_build_id),
                    retrieval_profile=await self.profiles.get_retrieval_profile(
                        variant.retrieval_profile_id
                    ),
                )
            )
        return views

    async def list(
        self, *, limit: int = 50, offset: int = 0
    ) -> tuple[
        Sequence[Experiment],
        dict[uuid.UUID, int],
        dict[uuid.UUID, SnapshotOrigin],
        int,
    ]:
        """One page of experiments, newest first, with the total.

        Each experiment comes with its variant count and the corpus and QA set its
        snapshots were frozen from, so a listing can group experiments by what they compare.
        """
        experiments = await self.experiments.list(limit=limit, offset=offset)
        ids = [item.id for item in experiments]
        return (
            experiments,
            await self.experiments.variant_counts(ids),
            await self.experiments.snapshot_origins(ids),
            await self.experiments.count(),
        )


class RunService:
    """The state of a run, read and written without needing Temporal.

    Following a run must not depend on the workflow engine being reachable, which is why
    the counters live on the run row; this class also holds what the worker's activities
    write into it.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.runs = RunRepository(session)
        self.executions = ExecutionRepository(session)
        self.experiments = ExperimentRepository(session)

    async def get(
        self, run_id: uuid.UUID, experiment_id: uuid.UUID | None = None
    ) -> Run:
        """Return a run, optionally checking that it belongs to an experiment.

        Raises:
            RunNotFoundError: If it does not exist or belongs to another experiment.
        """
        run = await self.runs.get_by_id(run_id)
        if run is None or (
            experiment_id is not None and run.experiment_id != experiment_id
        ):
            raise RunNotFoundError(run_id)
        return run

    async def refresh_progress(self, run: Run) -> dict[str, int]:
        """Copy the execution counters onto the run row for the UI to poll."""
        counts = await self.executions.count_by_status(run.id)
        total = sum(counts.values())
        succeeded = counts.get(ExecutionStatus.SUCCEEDED, 0)
        failed = counts.get(ExecutionStatus.FAILED, 0)
        run.progress = {
            "total": total,
            "succeeded": succeeded,
            "failed": failed,
            "pending": total - succeeded - failed,
        }
        await self.session.flush()
        return run.progress

    async def open_run(self, run_id: uuid.UUID) -> list[uuid.UUID]:
        """Mark a run `running` at the start of an attempt and return its variants.

        Executions an interrupted attempt left `running` go back to `pending`, so a
        relaunched run picks them up again.
        """
        run = await self.get(run_id)
        run.status = ExecutionStatus.RUNNING
        run.error = None
        run.finished_at = None
        run.started_at = run.started_at or dt.datetime.now(dt.UTC)
        await self.executions.reset_running(run_id)
        await self.refresh_progress(run)
        return [
            variant.id
            for variant in await self.experiments.list_variants(run.experiment_id)
        ]

    async def finish_run(self, run_id: uuid.UUID) -> None:
        """Score what did not succeed, aggregate the metrics and close the run.

        A run that went through every execution is `succeeded` even if some executions
        failed: the failures are counted on the run and excluded from the metrics with
        their reason, and relaunching the run retries just those.
        """
        run = await self.get(run_id)
        evaluation = EvaluationService(self.session)
        for execution in await self.executions.list_by_run(run_id):
            if execution.status != ExecutionStatus.SUCCEEDED:
                await evaluation.evaluate_execution(execution.id)
        await evaluation.aggregate_run(run_id)
        await evaluation.record_chunk_gold(
            run, await self.experiments.get_by_id(run.experiment_id)
        )
        await self.refresh_progress(run)
        run.status = ExecutionStatus.SUCCEEDED
        run.finished_at = dt.datetime.now(dt.UTC)
        await self.session.flush()

    async def evaluate_run(self, run_id: uuid.UUID, experiment_id: uuid.UUID) -> Run:
        """Score a finished run again from its stored hits, on the evidence as it is now.

        Annotating questions after a run gives it chunk metrics it did not have, and
        changing the evidence changes them, so re-scoring is an explicit action and never a
        side effect of reading the results. No retrieval is repeated: every execution is
        re-scored from the hits it recorded, the aggregates are rewritten, and the run
        records the fingerprint of the evidence it used. Document-level scores come out
        the same unless the gold documents changed.

        Raises:
            RunNotFoundError: If the run does not exist or belongs to another experiment.
            RunInProgressError: If the run has not finished.
        """
        run = await self.get(run_id, experiment_id)
        if run.status in (ExecutionStatus.PENDING, ExecutionStatus.RUNNING):
            raise RunInProgressError(run_id, run.status.value)
        evaluation = EvaluationService(self.session)
        for execution in await self.executions.list_by_run(run_id):
            await evaluation.evaluate_execution(execution.id)
        await evaluation.aggregate_run(run_id)
        await evaluation.record_chunk_gold(
            run, await self.experiments.get_by_id(run.experiment_id)
        )
        await self.session.refresh(run)
        return run

    async def fail_run(self, run_id: uuid.UUID, reason: str) -> None:
        """Record that a run stopped for a reason that is not one of its executions."""
        run = await self.get(run_id)
        await self.refresh_progress(run)
        run.status = ExecutionStatus.FAILED
        run.error = reason
        run.finished_at = dt.datetime.now(dt.UTC)
        await self.session.flush()


class RunLauncher:
    """Launch, relaunch and cancel the runs of an experiment."""

    def __init__(self, session: AsyncSession, workflows: WorkflowClient) -> None:
        self.session = session
        self.workflows = workflows
        self.experiments = ExperimentService(session)
        self.runs = RunService(session)
        self.qa_snapshots = QASetSnapshotRepository(session)
        self.executions = ExecutionRepository(session)
        self.profiles = ProfileService(session)

    async def start(
        self, experiment_id: uuid.UUID, *, concurrency: int | None = None
    ) -> RunLaunch:
        """Create a run of an experiment and start its workflow.

        The run keeps a full copy by value of the experiment, its variants, index builds and
        profiles as they are now, so the results stay interpretable if a profile is later
        replaced. Every execution (question x variant x repetition) is created `pending`
        up front: the run knows its size from the start, and a relaunch only has to look for
        the ones that did not succeed.

        Raises:
            ExperimentNotFoundError: If the experiment does not exist.
            IndexBuildNotReadyError: If a variant's index build is not `ready`.
        """
        experiment = await self.experiments.get(experiment_id)
        variants = await self.experiments.variant_views(experiment_id)
        for view in variants:
            if view.index_build.status != ArtifactStatus.READY:
                raise IndexBuildNotReadyError(
                    view.index_build.id, view.index_build.status.value
                )

        run = self.runs.runs.add(
            Run(
                experiment_id=experiment_id,
                status=ExecutionStatus.PENDING,
                config_snapshot=await self._config_snapshot(
                    experiment, variants, concurrency or DEFAULT_RUN_CONCURRENCY
                ),
            )
        )
        await self.session.flush()
        run.workflow_id = run_experiment_workflow_id(run.id)

        question_ids = await self.qa_snapshots.question_ids(
            experiment.qa_set_snapshot_id
        )
        await self.executions.add_many(
            [
                {
                    "run_id": run.id,
                    "variant_id": view.variant.id,
                    "question_id": question_id,
                    "repetition": repetition,
                }
                for view in variants
                for question_id in question_ids
                for repetition in range(1, experiment.repetitions + 1)
            ]
        )
        await self.runs.refresh_progress(run)
        return await self._launch(run, concurrency or DEFAULT_RUN_CONCURRENCY)

    async def resume(self, run_id: uuid.UUID, *, experiment_id: uuid.UUID) -> RunLaunch:
        """Relaunch an interrupted or partly failed run, redoing only what did not succeed.

        The executions that succeeded keep their hits and scores; the workflow skips them.

        Raises:
            RunNotFoundError: If the run does not exist.
            RunNotResumableError: If it is still running, or every execution succeeded.
        """
        run = await self.runs.get(run_id, experiment_id)
        if run.status == ExecutionStatus.RUNNING:
            raise RunNotResumableError(run_id, "it is still running")
        progress = await self.runs.refresh_progress(run)
        if (
            run.status == ExecutionStatus.SUCCEEDED
            and progress["succeeded"] == progress["total"]
        ):
            raise RunNotResumableError(run_id, "every execution already succeeded")
        run.status = ExecutionStatus.PENDING
        run.error = None
        run.finished_at = None
        await self.session.flush()
        concurrency = run.config_snapshot.get("concurrency", DEFAULT_RUN_CONCURRENCY)
        return await self._launch(run, concurrency)

    async def cancel(self, run_id: uuid.UUID, *, experiment_id: uuid.UUID) -> Run:
        """Cancel a run, recording `cancelled` as its reason.

        The executions that did not run stay `pending`, so the run can be resumed.

        Raises:
            RunNotFoundError: If the run does not exist.
            RunNotCancellableError: If the run already finished.
        """
        run = await self.runs.get(run_id, experiment_id)
        if run.status in (ExecutionStatus.SUCCEEDED, ExecutionStatus.FAILED):
            raise RunNotCancellableError(run_id, run.status.value)
        if run.workflow_id is not None:
            await self.workflows.cancel(run.workflow_id)
        # Marked here and not by the workflow: a cancelled workflow may never run another
        # activity, and a run left `running` forever is worse than one that says so.
        await self.runs.fail_run(run_id, CANCELLED_REASON)
        return run

    async def _launch(self, run: Run, concurrency: int) -> RunLaunch:
        outcome = await self.workflows.start(
            RUN_EXPERIMENT_WORKFLOW,
            arg={"run_id": str(run.id), "concurrency": concurrency},
            workflow_id=run.workflow_id or run_experiment_workflow_id(run.id),
            task_queue=EXPERIMENTS_TASK_QUEUE,
        )
        return RunLaunch(run=run, started=outcome.started)

    async def _config_snapshot(
        self, experiment: Experiment, variants: list[VariantView], concurrency: int
    ) -> dict[str, Any]:
        corpus_snapshot = await CorpusSnapshotRepository(self.session).get_by_id(
            experiment.corpus_snapshot_id
        )
        qa_snapshot = await self.qa_snapshots.get_by_id(experiment.qa_set_snapshot_id)
        return {
            "concurrency": concurrency,
            "experiment": {
                "id": str(experiment.id),
                "name": experiment.name,
                "type": experiment.type.value,
                "repetitions": experiment.repetitions,
                "retrieval_scope": experiment.retrieval_scope.value,
                "uncovered_policy": experiment.uncovered_policy,
            },
            "corpus_snapshot": {
                "id": str(corpus_snapshot.id),
                "corpus_id": str(corpus_snapshot.corpus_id),
                "label": corpus_snapshot.label,
                "document_count": corpus_snapshot.document_count,
                "composition_hash": corpus_snapshot.composition_hash,
            },
            "qa_set_snapshot": {
                "id": str(qa_snapshot.id),
                "label": qa_snapshot.label,
                "question_count": qa_snapshot.question_count,
                "composition_hash": qa_snapshot.composition_hash,
            },
            "variants": [await self._variant_snapshot(view) for view in variants],
        }

    async def _variant_snapshot(self, view: VariantView) -> dict[str, Any]:
        build = view.index_build
        profile = view.retrieval_profile
        embedding = await self.profiles.get_embedding_profile(
            build.embedding_profile_id
        )
        vector_store = await self.profiles.get_vector_store_profile(
            build.vector_store_profile_id
        )
        return {
            "id": str(view.variant.id),
            "name": view.variant.name,
            "is_baseline": view.variant.is_baseline,
            "index_build": {
                "id": str(build.id),
                "name": build.name,
                "chain_fingerprint": build.chain_fingerprint,
                "external_index_ref": build.external_index_ref,
                "chunking_configuration_id": str(build.chunking_configuration_id),
            },
            "embedding_profile": {
                "id": str(embedding.id),
                "name": embedding.name,
                "config_hash": embedding.config_hash,
                "params": dict(embedding.params),
            },
            "vector_store_profile": {
                "id": str(vector_store.id),
                "name": vector_store.name,
                "config_hash": vector_store.config_hash,
                "index_params": dict(vector_store.index_params),
            },
            "retrieval_profile": {
                "id": str(profile.id),
                "name": profile.name,
                "config_hash": profile.config_hash,
                "strategy": profile.strategy.value,
                "top_k": profile.top_k,
                "score_threshold": profile.score_threshold,
            },
        }
