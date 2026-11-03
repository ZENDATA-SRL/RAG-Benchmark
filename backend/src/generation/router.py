from __future__ import annotations

import dataclasses
import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from src.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page
from src.dependencies import SessionDep, WorkflowsDep
from src.generation.schemas import (
    CorpusDocumentRead,
    EstimateRead,
    EstimateResult,
    GenerationCreate,
    GenerationCreated,
    GenerationProgressRead,
    GenerationRead,
    ProposalAccept,
    ProposalChunkRead,
    ProposalDecision,
    ProposalRead,
    ProposalReject,
    ProposalReviewRead,
    UnitRead,
    UnmaterializedDocumentRead,
)
from src.generation.service import (
    GenerationService,
    GenerationView,
    ProposalView,
    ReviewService,
)
from src.infrastructure.database.enums import GeneratedKind, ProposalStatus

router = APIRouter(prefix="/generation-jobs", tags=["generation"])
proposals_router = APIRouter(prefix="/generated-questions", tags=["generation"])


def _excluded(items) -> list[UnmaterializedDocumentRead]:
    return [
        UnmaterializedDocumentRead(document_id=document_id, filename=filename)
        for document_id, filename in items
    ]


def _read(view: GenerationView) -> GenerationRead:
    job = view.job
    return GenerationRead(
        id=job.id,
        qa_set_id=job.qa_set_id,
        chunking_configuration_id=job.chunking_configuration_id,
        document_ids=list(job.document_ids),
        status=job.status,
        params=job.params,
        prompt_version=job.prompt_version,
        progress=GenerationProgressRead(**dataclasses.asdict(view.progress)),
        estimate=EstimateRead(**dataclasses.asdict(view.estimate)),
        error=job.error,
        created_at=job.created_at,
    )


def _proposal(view: ProposalView) -> ProposalRead:
    proposal = view.proposal
    return ProposalRead(
        id=proposal.id,
        generation_job_id=proposal.generation_job_id,
        kind=proposal.kind,
        text=proposal.text,
        answer=proposal.answer,
        status=proposal.status,
        accepted_question_id=proposal.accepted_question_id,
        reviewed_by=proposal.reviewed_by,
        reviewed_at=proposal.reviewed_at,
        created_at=proposal.created_at,
        chunks=[
            ProposalChunkRead(
                chunk_id=row.chunk.chunk_id,
                document_id=row.chunk.document_id,
                filename=row.chunk.filename,
                ordinal=row.chunk.ordinal,
                page=row.chunk.page,
                text=row.chunk.text,
                quote=row.link.quote,
                relevance=row.link.relevance,
                rank=row.link.rank,
            )
            for row in view.chunks
        ],
    )


def _planning(payload: GenerationCreate) -> dict:
    return {
        "qa_set_id": payload.qa_set_id,
        "chunking_configuration_id": payload.chunking_configuration_id,
        "per_document": payload.per_document,
        "cross_document": payload.cross_document,
        "document_ids": payload.document_ids,
        "excluded_document_ids": payload.excluded_document_ids,
        "exclude_unmaterialized": payload.exclude_unmaterialized,
        "max_steps": payload.max_steps,
    }


@router.post("/estimate", response_model=EstimateResult)
async def estimate_generation(
    payload: GenerationCreate, session: SessionDep
) -> EstimateResult:
    """Validate a job and say what it would cost, without creating anything."""
    plan = await GenerationService(session).plan(**_planning(payload))
    return EstimateResult(
        estimate=EstimateRead(**dataclasses.asdict(plan.estimate)),
        excluded=_excluded(plan.excluded),
        documents=[
            CorpusDocumentRead(
                document_id=state.document_id,
                filename=state.filename,
                materialised=state.materialised,
                excluded=state.document_id in plan.left_out,
            )
            for state in plan.corpus
        ],
    )


@router.post("", response_model=GenerationCreated, status_code=status.HTTP_202_ACCEPTED)
async def create_generation(
    payload: GenerationCreate, session: SessionDep, workflows: WorkflowsDep
) -> GenerationCreated:
    """Create a job generating questions and start it on the worker."""
    planning = _planning(payload)
    view = await GenerationService(session, workflows).create(
        **planning,
        provider=payload.provider,
        model=payload.model,
        region=payload.region,
        temperature=payload.temperature,
        language=payload.language,
        instructions=payload.instructions,
        concurrency=payload.concurrency,
    )
    return GenerationCreated(
        **_read(view).model_dump(), excluded=_excluded(view.excluded)
    )


@router.get("", response_model=Page[GenerationRead])
async def list_generations(
    session: SessionDep,
    qa_set_id: Annotated[uuid.UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[GenerationRead]:
    """List the jobs, newest first, optionally of one QA set."""
    views, total = await GenerationService(session).list(
        qa_set_id=qa_set_id, limit=limit, offset=offset
    )
    return Page[GenerationRead].build(
        [_read(view) for view in views], total=total, limit=limit, offset=offset
    )


@router.get("/{generation_job_id}", response_model=GenerationRead)
async def get_generation(
    generation_job_id: uuid.UUID, session: SessionDep
) -> GenerationRead:
    """Return a job with its progress, discards and coverage."""
    service = GenerationService(session)
    return _read(await service.view(await service.get(generation_job_id)))


@router.get("/{generation_job_id}/units", response_model=list[UnitRead])
async def list_generation_units(
    generation_job_id: uuid.UUID, session: SessionDep
) -> list[UnitRead]:
    """The runs of the agent of a job, with their target, outcome and trace."""
    return [
        UnitRead(
            id=view.unit.id,
            phase=view.unit.phase,
            position=view.unit.position,
            document_id=view.unit.document_id,
            filename=view.filename,
            target=view.unit.target,
            produced=view.unit.produced,
            status=view.unit.status,
            end_reason=view.unit.end_reason,
            error=view.unit.error,
            summary=view.unit.summary,
            topics=list(view.unit.topics or []),
            discards=dict(view.unit.discards or {}),
            trace_url=view.trace_url,
        )
        for view in await GenerationService(session).units_of(generation_job_id)
    ]


@router.post("/{generation_job_id}/cancel", response_model=GenerationRead)
async def cancel_generation(
    generation_job_id: uuid.UUID, session: SessionDep, workflows: WorkflowsDep
) -> GenerationRead:
    """Stop a job; the questions already proposed stay reviewable."""
    return _read(await GenerationService(session, workflows).cancel(generation_job_id))


@router.post(
    "/{generation_job_id}/resume",
    response_model=GenerationRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def resume_generation(
    generation_job_id: uuid.UUID, session: SessionDep, workflows: WorkflowsDep
) -> GenerationRead:
    """Relaunch a job, running only the units that did not succeed."""
    return _read(await GenerationService(session, workflows).resume(generation_job_id))


@router.get("/{generation_job_id}/proposals", response_model=Page[ProposalRead])
async def list_proposals(
    generation_job_id: uuid.UUID,
    session: SessionDep,
    status_filter: Annotated[ProposalStatus | None, Query(alias="status")] = None,
    kind: Annotated[GeneratedKind | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[ProposalRead]:
    """The review queue: the proposals of a job in the order they were saved."""
    views, total = await ReviewService(session).list(
        generation_job_id, status=status_filter, kind=kind, limit=limit, offset=offset
    )
    return Page[ProposalRead].build(
        [_proposal(view) for view in views], total=total, limit=limit, offset=offset
    )


@proposals_router.get("/{proposal_id}", response_model=ProposalReviewRead)
async def get_proposal(
    proposal_id: uuid.UUID,
    session: SessionDep,
    kind: Annotated[GeneratedKind | None, Query()] = None,
) -> ProposalReviewRead:
    """A proposal opened for review, with the next one waiting (of a kind, if given)."""
    review = await ReviewService(session).review(proposal_id, kind=kind)
    return ProposalReviewRead(
        **_proposal(review.view).model_dump(),
        qa_set_id=review.job.qa_set_id,
        chunking_configuration_id=review.job.chunking_configuration_id,
        phase=review.phase,
        trace_url=review.trace_url,
        next_proposal_id=review.next_proposal_id,
    )


@proposals_router.post("/{proposal_id}/accept", response_model=ProposalDecision)
async def accept_proposal(
    proposal_id: uuid.UUID, payload: ProposalAccept, session: SessionDep
) -> ProposalDecision:
    """Accept a proposal, corrected or not: it becomes a question with confirmed evidence."""
    decision = await ReviewService(session).accept(
        proposal_id,
        text=payload.text,
        answer=payload.answer,
        chunks=[(chunk.chunk_id, chunk.relevance) for chunk in payload.chunks],
        annotator=payload.annotator,
    )
    return ProposalDecision(
        proposal=_proposal(decision.view),
        question_id=decision.question_id,
        next_proposal_id=decision.next_proposal_id,
    )


@proposals_router.post("/{proposal_id}/reject", response_model=ProposalDecision)
async def reject_proposal(
    proposal_id: uuid.UUID, payload: ProposalReject, session: SessionDep
) -> ProposalDecision:
    """Reject a proposal; it leaves no trace in the set."""
    decision = await ReviewService(session).reject(
        proposal_id, annotator=payload.annotator
    )
    return ProposalDecision(
        proposal=_proposal(decision.view),
        question_id=None,
        next_proposal_id=decision.next_proposal_id,
    )
