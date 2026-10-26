from __future__ import annotations

import dataclasses
import uuid

from src.experiments.evaluation import ExecutionRunner
from src.experiments.repository import ExecutionRepository
from src.experiments.service import RunService
from temporalio import activity

from temporal.config import activity_session


@dataclasses.dataclass
class ExperimentRunResolved:
    """The variants a run has to go through, as ids: nothing here grows with the questions."""

    variant_ids: list[str]


@activity.defn
async def open_experiment_run(run_id: str) -> ExperimentRunResolved:
    """Mark a run `running` for this attempt and return its variants.

    Executions a previous, interrupted attempt left `running` go back to `pending`.
    """
    async with activity_session() as session:
        variant_ids = await RunService(session).open_run(uuid.UUID(run_id))
        return ExperimentRunResolved(variant_ids=[str(item) for item in variant_ids])


@activity.defn
async def list_unfinished_executions(
    run_id: str, variant_id: str, after_id: str | None, limit: int
) -> list[str]:
    """One page of the executions of a variant that did not succeed yet, after a cursor.

    The workflow asks for pages instead of receiving every execution id, so a run over
    thousands of questions never puts the whole list in a payload or in its history.
    """
    async with activity_session() as session:
        ids = await ExecutionRepository(session).unfinished_ids(
            uuid.UUID(run_id),
            uuid.UUID(variant_id),
            after_id=uuid.UUID(after_id) if after_id else None,
            limit=limit,
        )
        return [str(item) for item in ids]


@activity.defn
async def retrieve_question(execution_id: str) -> str:
    """Retrieve for one execution, record the hits and score them; returns its status.

    A permanent error on the question marks the execution `failed` and returns normally,
    so the run goes on. A failure of the embedder or the vector store is raised for the
    workflow to retry with backoff.
    """
    async with activity_session() as session:
        outcome = await ExecutionRunner(session).run(uuid.UUID(execution_id))
        return outcome.status.value


@activity.defn
async def mark_execution_failed(execution_id: str, error: str) -> None:
    """Record that an execution kept failing after its retries, with the reason."""
    async with activity_session() as session:
        await ExecutionRunner(session).fail(uuid.UUID(execution_id), error)


@activity.defn
async def record_run_progress(run_id: str) -> None:
    """Copy the execution counters onto the run row for the UI to poll."""
    async with activity_session() as session:
        service = RunService(session)
        await service.refresh_progress(await service.get(uuid.UUID(run_id)))


@activity.defn
async def finish_experiment_run(run_id: str) -> None:
    """Score the executions that did not succeed, aggregate the metrics and close the run."""
    async with activity_session() as session:
        await RunService(session).finish_run(uuid.UUID(run_id))


@activity.defn
async def fail_experiment_run(run_id: str, reason: str) -> None:
    """Close a run that stopped for a reason of its own, so it does not stay `running`."""
    async with activity_session() as session:
        await RunService(session).fail_run(uuid.UUID(run_id), reason)
