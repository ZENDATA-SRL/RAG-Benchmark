from __future__ import annotations

import uuid

from src.transfers.ranking import TransferRanker
from temporalio import activity

from temporal.config import activity_session


@activity.defn
async def open_transfer_job(transfer_job_id: str) -> None:
    """Mark a job `running` for this attempt; questions left `running` go back to pending."""
    async with activity_session() as session:
        await TransferRanker(session).open_job(uuid.UUID(transfer_job_id))


@activity.defn
async def list_unranked_questions(
    transfer_job_id: str, after_id: str | None, limit: int
) -> list[str]:
    """One page of the questions of a job not ranked yet, after a cursor."""
    async with activity_session() as session:
        ids = await TransferRanker(session).unfinished_ids(
            uuid.UUID(transfer_job_id),
            after_id=uuid.UUID(after_id) if after_id else None,
            limit=limit,
        )
        return [str(item) for item in ids]


@activity.defn
async def rank_transfer_question(transfer_question_id: str) -> str:
    """Rank the candidate chunks of one question of a job; returns its status.

    A failure of the embedder is raised for the workflow to retry with backoff; any other
    error of the question marks it `failed` and returns, so the job goes on.
    """
    async with activity_session() as session:
        outcome = await TransferRanker(session).rank(uuid.UUID(transfer_question_id))
        return outcome.status.value


@activity.defn
async def mark_transfer_question_failed(transfer_question_id: str, error: str) -> None:
    """Record that a question kept failing after its retries, with the reason."""
    async with activity_session() as session:
        await TransferRanker(session).fail(uuid.UUID(transfer_question_id), error)


@activity.defn
async def record_transfer_progress(transfer_job_id: str) -> None:
    """Copy the progress and the recall ceiling onto the job row."""
    async with activity_session() as session:
        await TransferRanker(session).record_progress(uuid.UUID(transfer_job_id))


@activity.defn
async def finish_transfer_job(transfer_job_id: str) -> None:
    """Close a job whose questions were all attempted."""
    async with activity_session() as session:
        await TransferRanker(session).finish_job(uuid.UUID(transfer_job_id))


@activity.defn
async def fail_transfer_job(transfer_job_id: str, reason: str) -> None:
    """Close a job that stopped for a reason of its own, so it does not stay `running`."""
    async with activity_session() as session:
        await TransferRanker(session).fail_job(uuid.UUID(transfer_job_id), reason)
