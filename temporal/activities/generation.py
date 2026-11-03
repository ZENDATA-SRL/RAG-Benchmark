from __future__ import annotations

import dataclasses
import uuid

from src.generation.runner import GenerationRunner
from src.infrastructure.database.enums import GenerationPhase
from src.infrastructure.observability import get_tracer
from temporalio import activity

from temporal.config import activity_session


@dataclasses.dataclass
class GenerationUnitRef:
    """A unit as the workflow pages through them: its id and its place in the phase."""

    unit_id: str
    position: int


@activity.defn
async def open_generation_job(generation_job_id: str) -> bool:
    """Mark a job `running` for this attempt; whether it has anything to run.

    A job whose provider has no credentials on this worker fails here, with the reason,
    and returns `False` so the workflow ends without attempting any unit.
    """
    async with activity_session() as session:
        return await GenerationRunner(session).open_job(uuid.UUID(generation_job_id))


@activity.defn
async def list_generation_units(
    generation_job_id: str, phase: str, after_position: int | None, limit: int
) -> list[GenerationUnitRef]:
    """One page of the units of a phase not done yet, in their order, after a cursor."""
    async with activity_session() as session:
        units = await GenerationRunner(session).unfinished_units(
            uuid.UUID(generation_job_id),
            GenerationPhase(phase),
            after_position=after_position,
            limit=limit,
        )
        return [GenerationUnitRef(unit.unit_id, unit.position) for unit in units]


@activity.defn
async def run_generation_unit(unit_id: str) -> str:
    """Let the agent write the questions of one unit; returns the unit's status.

    Runs on the `llm` queue. It heartbeats on every tool the agent calls, so a worker
    that dies mid-unit is noticed in a couple of minutes rather than at the end of the
    timeout. A failure of the model provider is raised for the workflow to retry: the
    questions already saved stay, and the retry asks only for what is left.

    The trace is flushed before returning, so a worker stopped right after does not lose it.
    """
    tracer = get_tracer()
    try:
        async with activity_session() as session:
            status = await GenerationRunner(session, tracer).run_unit(
                uuid.UUID(unit_id), on_step=activity.heartbeat
            )
            return status.value
    finally:
        await tracer.flush()


@activity.defn
async def mark_generation_unit_failed(unit_id: str, error: str) -> None:
    """Record that a unit kept failing after its retries, with the reason."""
    async with activity_session() as session:
        await GenerationRunner(session).fail_unit(uuid.UUID(unit_id), error)


@activity.defn
async def record_generation_progress(generation_job_id: str) -> None:
    """Copy the counters of the units and the proposals onto the job row."""
    async with activity_session() as session:
        await GenerationRunner(session).record_progress(uuid.UUID(generation_job_id))


@activity.defn
async def finish_generation_job(generation_job_id: str) -> None:
    """Close a job whose units were all attempted."""
    async with activity_session() as session:
        await GenerationRunner(session).finish_job(uuid.UUID(generation_job_id))


@activity.defn
async def fail_generation_job(generation_job_id: str, reason: str) -> None:
    """Close a job that stopped for a reason of its own, so it does not stay `running`."""
    async with activity_session() as session:
        await GenerationRunner(session).fail_job(uuid.UUID(generation_job_id), reason)
