from __future__ import annotations

import dataclasses
import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, Query, Response, status

from src.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page
from src.dependencies import SessionDep, WorkflowsDep
from src.experiments.results import ResultsService
from src.experiments.schemas import (
    CoverageRead,
    ExperimentCreate,
    ExperimentDetail,
    ExperimentRead,
    QuestionDrilldownRead,
    RunAccepted,
    RunDetail,
    RunLaunchRequest,
    RunQuestionRead,
    RunRead,
    RunResultsRead,
    UncoveredDocumentRead,
    UncoveredQuestionRead,
    VariantRead,
)
from src.experiments.service import (
    CoverageReport,
    ExperimentService,
    ExperimentView,
    RunLaunch,
    RunLauncher,
    RunService,
    VariantInput,
    VariantView,
)

if TYPE_CHECKING:
    from src.experiments.models import Experiment
    from src.experiments.service import SnapshotOrigin

router = APIRouter(prefix="/experiments", tags=["experiments"])


def _coverage_read(report: CoverageReport) -> CoverageRead:
    return CoverageRead(
        question_count=report.question_count,
        uncovered_count=len(report.uncovered),
        uncovered=[
            UncoveredQuestionRead(
                question_id=question.question_id,
                text=question.text,
                missing_documents=[
                    UncoveredDocumentRead(document_id=document_id, filename=filename)
                    for document_id, filename in question.missing_documents
                ],
            )
            for question in report.uncovered
        ],
    )


def _variant_read(view: VariantView) -> VariantRead:
    return VariantRead(
        id=view.variant.id,
        name=view.variant.name,
        is_baseline=view.variant.is_baseline,
        index_build_id=view.index_build.id,
        index_build_name=view.index_build.name,
        index_build_status=view.index_build.status,
        retrieval_profile_id=view.retrieval_profile.id,
        retrieval_profile_name=view.retrieval_profile.name,
        top_k=view.retrieval_profile.top_k,
    )


def _experiment_read(
    experiment: Experiment, variant_count: int, origin: SnapshotOrigin | None
) -> ExperimentRead:
    item = ExperimentRead.model_validate(experiment)
    item.variant_count = variant_count
    if origin is not None:
        item = item.model_copy(update=dataclasses.asdict(origin))
    return item


def _detail(view: ExperimentView) -> ExperimentDetail:
    base = _experiment_read(view.experiment, len(view.variants), view.origin)
    return ExperimentDetail(
        **base.model_dump(),
        variants=[_variant_read(variant) for variant in view.variants],
        runs=[RunRead.model_validate(run) for run in view.runs],
        coverage=_coverage_read(view.coverage),
    )


def _accepted(launch: RunLaunch) -> RunAccepted:
    return RunAccepted(
        **RunRead.model_validate(launch.run).model_dump(),
        started=launch.started,
        detail=None
        if launch.started
        else "the workflow of this run was already running and is reported instead",
    )


@router.post("", response_model=ExperimentDetail, status_code=status.HTTP_201_CREATED)
async def create_experiment(
    payload: ExperimentCreate, session: SessionDep
) -> ExperimentDetail:
    """Create an experiment, refusing variants on another snapshot and uncovered gold."""
    service = ExperimentService(session)
    experiment = await service.create(
        name=payload.name,
        type=payload.type,
        corpus_snapshot_id=payload.corpus_snapshot_id,
        qa_set_snapshot_id=payload.qa_set_snapshot_id,
        repetitions=payload.repetitions,
        variants=[
            VariantInput(
                name=variant.name,
                index_build_id=variant.index_build_id,
                retrieval_profile_id=variant.retrieval_profile_id,
                is_baseline=variant.is_baseline,
            )
            for variant in payload.variants
        ],
        uncovered_policy=payload.uncovered_policy,
    )
    return _detail(await service.detail(experiment.id))


@router.get("", response_model=Page[ExperimentRead])
async def list_experiments(
    session: SessionDep,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> Page[ExperimentRead]:
    """List the experiments, newest first."""
    experiments, counts, origins, total = await ExperimentService(session).list(
        limit=limit, offset=offset
    )
    items = [
        _experiment_read(
            experiment, counts.get(experiment.id, 0), origins.get(experiment.id)
        )
        for experiment in experiments
    ]
    return Page[ExperimentRead].build(items, total=total, limit=limit, offset=offset)


@router.get("/coverage", response_model=CoverageRead)
async def check_coverage(
    session: SessionDep, corpus_snapshot_id: uuid.UUID, qa_set_snapshot_id: uuid.UUID
) -> CoverageRead:
    """List the questions whose gold documents are not all in a corpus snapshot."""
    return _coverage_read(
        await ExperimentService(session).coverage(
            corpus_snapshot_id, qa_set_snapshot_id
        )
    )


@router.get("/{experiment_id}", response_model=ExperimentDetail)
async def get_experiment(
    experiment_id: uuid.UUID, session: SessionDep
) -> ExperimentDetail:
    """Return an experiment with its variants, runs and gold coverage."""
    return _detail(await ExperimentService(session).detail(experiment_id))


@router.post(
    "/{experiment_id}/runs",
    response_model=RunAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_run(
    experiment_id: uuid.UUID,
    session: SessionDep,
    workflows: WorkflowsDep,
    payload: RunLaunchRequest | None = None,
) -> RunAccepted:
    """Create a run of an experiment and start it on Temporal."""
    launch = await RunLauncher(session, workflows).start(
        experiment_id, concurrency=payload.concurrency if payload else None
    )
    return _accepted(launch)


@router.get("/{experiment_id}/runs/{run_id}", response_model=RunDetail)
async def get_run(
    experiment_id: uuid.UUID, run_id: uuid.UUID, session: SessionDep
) -> RunDetail:
    """Return a run with its progress and the configuration copied at launch.

    Served from the denormalised row, so polling it never depends on Temporal.
    """
    run = await RunService(session).get(run_id, experiment_id)
    return RunDetail.model_validate(run)


@router.post(
    "/{experiment_id}/runs/{run_id}/resume",
    response_model=RunAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def resume_run(
    experiment_id: uuid.UUID,
    run_id: uuid.UUID,
    session: SessionDep,
    workflows: WorkflowsDep,
) -> RunAccepted:
    """Relaunch an interrupted or partly failed run, redoing only what did not succeed."""
    launch = await RunLauncher(session, workflows).resume(
        run_id, experiment_id=experiment_id
    )
    return _accepted(launch)


@router.post("/{experiment_id}/runs/{run_id}/cancel", response_model=RunRead)
async def cancel_run(
    experiment_id: uuid.UUID,
    run_id: uuid.UUID,
    session: SessionDep,
    workflows: WorkflowsDep,
) -> RunRead:
    """Cancel a running run, recording `cancelled` as its reason."""
    run = await RunLauncher(session, workflows).cancel(
        run_id, experiment_id=experiment_id
    )
    return RunRead.model_validate(run)


@router.post("/{experiment_id}/runs/{run_id}/evaluate", response_model=RunDetail)
async def evaluate_run(
    experiment_id: uuid.UUID, run_id: uuid.UUID, session: SessionDep
) -> RunDetail:
    """Re-score a finished run from its stored hits, on the evidence as it is now."""
    run = await RunService(session).evaluate_run(run_id, experiment_id)
    return RunDetail.model_validate(run)


@router.get("/{experiment_id}/runs/{run_id}/results", response_model=RunResultsRead)
async def get_results(
    experiment_id: uuid.UUID,
    run_id: uuid.UUID,
    session: SessionDep,
    tag: str | None = Query(
        default=None, description="Aggregate over one question tag."
    ),
) -> RunResultsRead:
    """Return the aggregated metrics per variant, with effective and excluded counts."""
    return await ResultsService(session).results(
        experiment_id,
        run_id,
        slice_key="tag" if tag else "all",
        slice_value=tag or "all",
    )


@router.get("/{experiment_id}/runs/{run_id}/results.csv")
async def get_results_csv(
    experiment_id: uuid.UUID, run_id: uuid.UUID, session: SessionDep
) -> Response:
    """Download the aggregated metrics of a run as CSV."""
    content = await ResultsService(session).results_csv(experiment_id, run_id)
    return Response(
        content=content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="run-{run_id}-results.csv"'
        },
    )


@router.get(
    "/{experiment_id}/runs/{run_id}/questions", response_model=Page[RunQuestionRead]
)
async def list_run_questions(
    experiment_id: uuid.UUID,
    run_id: uuid.UUID,
    session: SessionDep,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> Page[RunQuestionRead]:
    """List the questions of a run with the outcome of each variant."""
    rows, total = await ResultsService(session).list_questions(
        experiment_id, run_id, limit=limit, offset=offset
    )
    return Page[RunQuestionRead].build(rows, total=total, limit=limit, offset=offset)


@router.get(
    "/{experiment_id}/runs/{run_id}/questions/{question_id}",
    response_model=QuestionDrilldownRead,
)
async def get_run_question(
    experiment_id: uuid.UUID,
    run_id: uuid.UUID,
    question_id: uuid.UUID,
    session: SessionDep,
) -> QuestionDrilldownRead:
    """Return what each variant retrieved for a question, hit by hit."""
    return await ResultsService(session).question_detail(
        experiment_id, run_id, question_id
    )
