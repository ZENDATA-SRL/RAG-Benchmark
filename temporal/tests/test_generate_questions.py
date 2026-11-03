from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import uuid

import pytest
from temporalio import activity
from temporalio.client import WorkflowFailureError
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from temporal.activities.generation import GenerationUnitRef
from temporal.task_queues import WORKER_TASK_QUEUES, TaskQueue
from temporal.workflows.generate_questions import (
    GenerateQuestionsInput,
    GenerateQuestionsWorkflow,
)

pytestmark = pytest.mark.asyncio


@dataclasses.dataclass
class Unit:
    unit_id: str
    phase: str
    position: int
    status: str = "pending"


@dataclasses.dataclass
class Job:
    """The state the mocked activities share, standing in for `generation_units`."""

    units: list[Unit]
    ready: bool = True
    failing: set[str] = dataclasses.field(default_factory=set)
    attempts: dict[str, int] = dataclasses.field(default_factory=dict)
    order: list[str] = dataclasses.field(default_factory=list)
    running: int = 0
    max_running: dict[str, int] = dataclasses.field(default_factory=dict)
    opened: int = 0
    finished: int = 0
    failed_jobs: list[str] = dataclasses.field(default_factory=list)
    marked_failed: list[str] = dataclasses.field(default_factory=list)
    open_error: Exception | None = None


def _job(documents: int = 3, cross: int = 2) -> Job:
    units = [Unit(str(uuid.uuid4()), "document", i) for i in range(documents)]
    units += [Unit(str(uuid.uuid4()), "cross", i) for i in range(cross)]
    return Job(units=units)


def _activities(state: Job):
    by_id = {unit.unit_id: unit for unit in state.units}

    @activity.defn(name="open_generation_job")
    async def open_generation_job(generation_job_id: str) -> bool:
        if state.open_error is not None:
            raise state.open_error
        state.opened += 1
        return state.ready

    @activity.defn(name="list_generation_units")
    async def list_generation_units(
        generation_job_id: str, phase: str, after_position: int | None, limit: int
    ) -> list[GenerationUnitRef]:
        units = sorted(
            (
                unit
                for unit in state.units
                if unit.phase == phase
                and unit.status != "succeeded"
                and (after_position is None or unit.position > after_position)
            ),
            key=lambda unit: unit.position,
        )
        return [GenerationUnitRef(u.unit_id, u.position) for u in units[:limit]]

    @activity.defn(name="run_generation_unit")
    async def run_generation_unit(unit_id: str) -> str:
        unit = by_id[unit_id]
        state.attempts[unit_id] = state.attempts.get(unit_id, 0) + 1
        state.running += 1
        state.max_running[unit.phase] = max(
            state.max_running.get(unit.phase, 0), state.running
        )
        try:
            await asyncio.sleep(0.01)
            if unit_id in state.failing:
                raise ApplicationError("provider is down")
            state.order.append(unit.phase)
            unit.status = "succeeded"
            return "succeeded"
        finally:
            state.running -= 1

    @activity.defn(name="mark_generation_unit_failed")
    async def mark_generation_unit_failed(unit_id: str, error: str) -> None:
        state.marked_failed.append(unit_id)
        by_id[unit_id].status = "failed"

    @activity.defn(name="record_generation_progress")
    async def record_generation_progress(generation_job_id: str) -> None:
        pass

    @activity.defn(name="finish_generation_job")
    async def finish_generation_job(generation_job_id: str) -> None:
        state.finished += 1

    @activity.defn(name="fail_generation_job")
    async def fail_generation_job(generation_job_id: str, reason: str) -> None:
        state.failed_jobs.append(reason)

    return [
        open_generation_job,
        list_generation_units,
        run_generation_unit,
        mark_generation_unit_failed,
        record_generation_progress,
        finish_generation_job,
        fail_generation_job,
    ]


@contextlib.asynccontextmanager
async def _environment(state: Job):
    async with await WorkflowEnvironment.start_time_skipping() as env:
        workers = [
            Worker(
                env.client,
                task_queue=queue.value,
                workflows=[GenerateQuestionsWorkflow],
                activities=_activities(state),
            )
            for queue in WORKER_TASK_QUEUES
        ]
        async with contextlib.AsyncExitStack() as stack:
            for worker in workers:
                await stack.enter_async_context(worker)
            yield env


async def _launch(env, concurrency: int = 4) -> dict:
    job_id = str(uuid.uuid4())
    return await env.client.execute_workflow(
        GenerateQuestionsWorkflow.run,
        GenerateQuestionsInput(generation_job_id=job_id, concurrency=concurrency),
        id=f"generate-questions-{job_id}",
        task_queue=TaskQueue.EXPERIMENTS.value,
    )


async def test_document_units_run_first_then_cross_units_one_at_a_time() -> None:
    state = _job(documents=4, cross=3)

    async with _environment(state) as env:
        result = await _launch(env)

    assert result["ran"] is True
    assert state.order == ["document"] * 4 + ["cross"] * 3
    assert state.max_running["document"] > 1
    assert state.max_running["cross"] == 1
    assert (state.opened, state.finished, state.failed_jobs) == (1, 1, [])


async def test_a_resumed_job_runs_only_the_units_left() -> None:
    state = _job(documents=3, cross=2)
    state.units[0].status = "succeeded"
    state.units[3].status = "succeeded"

    async with _environment(state) as env:
        await _launch(env)

    assert set(state.attempts) == {u.unit_id for u in state.units} - {
        state.units[0].unit_id,
        state.units[3].unit_id,
    }


async def test_a_unit_that_keeps_failing_does_not_stop_the_job() -> None:
    state = _job(documents=3, cross=1)
    broken = state.units[1].unit_id
    state.failing.add(broken)

    async with _environment(state) as env:
        await _launch(env)

    assert state.attempts[broken] == 5
    assert state.marked_failed == [broken]
    assert state.units[-1].status == "succeeded"
    assert state.finished == 1


async def test_a_job_without_credentials_stops_after_opening() -> None:
    state = _job()
    state.ready = False

    async with _environment(state) as env:
        result = await _launch(env)

    assert result["ran"] is False
    assert state.attempts == {}
    assert state.finished == 0


async def test_a_large_job_is_continued_as_new() -> None:
    state = _job(documents=230, cross=1)

    async with _environment(state) as env:
        await _launch(env, concurrency=10)

    assert len(state.attempts) == 231
    assert state.opened == 1
    assert state.finished == 1


async def test_a_failure_of_the_job_is_recorded_on_it() -> None:
    state = _job()
    state.open_error = ApplicationError("database gone", non_retryable=True)

    async with _environment(state) as env:
        with pytest.raises(WorkflowFailureError):
            await _launch(env)

    assert len(state.failed_jobs) == 1
    assert state.finished == 0
