from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from src.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page
from src.dependencies import SessionDep, WorkflowsDep
from src.materializations.schemas import (
    DocumentFailureRead,
    MaterializationAccepted,
    MaterializationCreate,
    MaterializationDetail,
    MaterializationRead,
)
from src.materializations.service import (
    MaterializationRunService,
    MaterializationService,
)

router = APIRouter(prefix="/materializations", tags=["materializations"])


@router.post(
    "", response_model=MaterializationAccepted, status_code=status.HTTP_202_ACCEPTED
)
async def start_materialization(
    payload: MaterializationCreate,
    session: SessionDep,
    workflows: WorkflowsDep,
) -> MaterializationAccepted:
    """Launch a materialisation, or report the run already doing the same work."""
    launch = await MaterializationService(session, workflows).start(
        chunking_configuration_id=payload.chunking_configuration_id,
        document_ids=payload.document_ids,
        corpus_id=payload.corpus_id,
        concurrency=payload.concurrency,
    )
    return MaterializationAccepted(
        **MaterializationRead.model_validate(launch.run).model_dump(),
        started=launch.started,
        detail=None
        if launch.started
        else "an identical materialisation was already running and is reported instead",
    )


@router.get("", response_model=Page[MaterializationRead])
async def list_materializations(
    session: SessionDep,
    corpus_id: uuid.UUID | None = Query(default=None),
    chunking_configuration_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> Page[MaterializationRead]:
    """List the materialisation history, newest first."""
    runs, total = await MaterializationRunService(session).list(
        corpus_id=corpus_id,
        chunking_configuration_id=chunking_configuration_id,
        limit=limit,
        offset=offset,
    )
    return Page[MaterializationRead].build(
        [MaterializationRead.model_validate(run) for run in runs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{run_id}", response_model=MaterializationDetail)
async def get_materialization(
    run_id: uuid.UUID, session: SessionDep
) -> MaterializationDetail:
    """Return the progress of a run; polled every couple of seconds by the UI (RT-U05).

    Served entirely from the denormalised row, so following a run never depends on Temporal
    being reachable.
    """
    service = MaterializationRunService(session)
    run = await service.get(run_id)
    return MaterializationDetail(
        **MaterializationRead.model_validate(run).model_dump(),
        failures=[
            DocumentFailureRead(document_id=failure.document_id, error=failure.error)
            for failure in await service.failures(run)
        ],
    )


@router.post("/{run_id}/cancel", response_model=MaterializationRead)
async def cancel_materialization(
    run_id: uuid.UUID, session: SessionDep, workflows: WorkflowsDep
) -> MaterializationRead:
    """Cancel a running materialisation, recording `cancelled` as its reason."""
    run = await MaterializationService(session, workflows).cancel(run_id)
    return MaterializationRead.model_validate(run)
