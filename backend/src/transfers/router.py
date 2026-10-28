from __future__ import annotations

import dataclasses
import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from src.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page
from src.dependencies import SessionDep, WorkflowsDep
from src.transfers.schemas import (
    CandidateRead,
    ExcludedQuestionRead,
    QuestionReviewRead,
    QueueRowRead,
    QueueState,
    ReferenceChunkRead,
    TransferCreate,
    TransferCreated,
    TransferProgressRead,
    TransferRead,
    UncoveredDocumentRead,
)
from src.transfers.service import TransferService, TransferView

router = APIRouter(prefix="/transfers", tags=["transfers"])


def _read(view: TransferView) -> TransferRead:
    job = view.job
    return TransferRead(
        id=job.id,
        qa_set_id=job.qa_set_id,
        source_configuration_id=job.source_configuration_id,
        target_configuration_id=job.target_configuration_id,
        embedding_profile_id=job.embedding_profile_id,
        status=job.status,
        signal_weights=job.signal_weights,
        confidence_thresholds=job.confidence_thresholds,
        progress=TransferProgressRead(**dataclasses.asdict(view.progress)),
        skipped=job.progress.get("skipped", {}),
        recall_ceiling=view.recall_ceiling,
        error=job.error,
        created_at=job.created_at,
    )


@router.post("", response_model=TransferCreated, status_code=status.HTTP_202_ACCEPTED)
async def create_transfer(
    payload: TransferCreate, session: SessionDep, workflows: WorkflowsDep
) -> TransferCreated:
    """Create a job proposing evidence chunks and start ranking them on the worker."""
    view = await TransferService(session, workflows).create(
        qa_set_id=payload.qa_set_id,
        target_configuration_id=payload.target_configuration_id,
        source_configuration_id=payload.source_configuration_id,
        embedding_profile_id=payload.embedding_profile_id,
        signal_weights=payload.signal_weights.model_dump(exclude_none=True)
        if payload.signal_weights
        else None,
        confidence_thresholds=payload.confidence_thresholds.model_dump(
            exclude_none=True
        )
        if payload.confidence_thresholds
        else None,
        question_ids=payload.question_ids,
        exclude_uncovered=payload.exclude_uncovered,
        concurrency=payload.concurrency,
    )
    return TransferCreated(
        **_read(view).model_dump(),
        excluded=[
            ExcludedQuestionRead(
                question_id=item.question_id,
                text=item.text,
                reason=item.reason,
                missing_documents=[
                    UncoveredDocumentRead(document_id=document_id, filename=filename)
                    for document_id, filename in item.missing_documents
                ],
            )
            for item in view.excluded
        ],
    )


@router.get("", response_model=Page[TransferRead])
async def list_transfers(
    session: SessionDep,
    qa_set_id: Annotated[uuid.UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[TransferRead]:
    """List the jobs, newest first, optionally of one QA set."""
    views, total = await TransferService(session).list(
        qa_set_id=qa_set_id, limit=limit, offset=offset
    )
    return Page[TransferRead].build(
        [_read(view) for view in views], total=total, limit=limit, offset=offset
    )


@router.get("/{transfer_job_id}", response_model=TransferRead)
async def get_transfer(transfer_job_id: uuid.UUID, session: SessionDep) -> TransferRead:
    """Return a job with its progress, read live from the evidence."""
    service = TransferService(session)
    return _read(await service.view(await service.get(transfer_job_id)))


@router.post("/{transfer_job_id}/cancel", response_model=TransferRead)
async def cancel_transfer(
    transfer_job_id: uuid.UUID, session: SessionDep, workflows: WorkflowsDep
) -> TransferRead:
    """Stop ranking; the candidates already written stay reviewable."""
    return _read(await TransferService(session, workflows).cancel(transfer_job_id))


@router.post(
    "/{transfer_job_id}/resume",
    response_model=TransferRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def resume_transfer(
    transfer_job_id: uuid.UUID, session: SessionDep, workflows: WorkflowsDep
) -> TransferRead:
    """Relaunch a job, ranking only the questions not ranked yet."""
    return _read(await TransferService(session, workflows).resume(transfer_job_id))


@router.get("/{transfer_job_id}/questions", response_model=Page[QueueRowRead])
async def list_transfer_questions(
    transfer_job_id: uuid.UUID,
    session: SessionDep,
    state: Annotated[QueueState | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[QueueRowRead]:
    """The review queue: questions waiting for a decision first, the near certain on top."""
    rows, total = await TransferService(session).queue(
        transfer_job_id, state=state, limit=limit, offset=offset
    )
    return Page[QueueRowRead].build(
        [QueueRowRead(**dataclasses.asdict(row)) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{transfer_job_id}/questions/{question_id}", response_model=QuestionReviewRead
)
async def get_transfer_question(
    transfer_job_id: uuid.UUID, question_id: uuid.UUID, session: SessionDep
) -> QuestionReviewRead:
    """A question opened for review, with its candidates best first.

    The decision is not written here: it is the question's evidence, saved with
    `PUT /questions/{question_id}/evidence` like any other annotation.
    """
    service = TransferService(session)
    job = await service.get(transfer_job_id)
    review = await service.review(transfer_job_id, question_id)
    return QuestionReviewRead(
        transfer_job_id=job.id,
        question_id=review.question.id,
        qa_set_id=review.question.qa_set_id,
        text=review.question.text,
        state=review.state,
        evidence_status=review.evidence_status,
        target_configuration_id=job.target_configuration_id,
        reference=[
            ReferenceChunkRead(
                chunk_id=source.chunk.id,
                document_id=source.document_id,
                ordinal=source.chunk.ordinal,
                page=source.chunk.chunk_metadata.get("page")
                if isinstance(source.chunk.chunk_metadata.get("page"), int)
                else None,
                text=source.chunk.text,
                relevance=source.relevance,
            )
            for source in review.reference
        ],
        candidates=[
            CandidateRead(
                chunk_id=item.candidate.chunk_id,
                document_id=item.document_id,
                filename=item.filename,
                ordinal=item.ordinal,
                page=item.page,
                text=item.chunk_text,
                rank=item.candidate.rank,
                combined_score=item.candidate.combined_score,
                semantic_score=item.candidate.semantic_score,
                lexical_score=item.candidate.lexical_score,
                positional_score=item.candidate.positional_score,
                confidence=item.candidate.confidence,
                preselected=item.candidate.preselected,
                suggested_relevance=item.candidate.suggested_relevance,
            )
            for item in review.candidates
        ],
        next_question_id=review.next_question_id,
    )
