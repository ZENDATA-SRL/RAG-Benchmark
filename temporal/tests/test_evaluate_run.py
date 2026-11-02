from __future__ import annotations

import contextlib
import dataclasses
import uuid

import pytest
from temporalio import activity
from temporalio.client import WorkflowFailureError
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from temporal.task_queues import TaskQueue
from temporal.workflows.evaluate_run import EvaluateRunInput, EvaluateRunWorkflow

pytestmark = pytest.mark.asyncio


@dataclasses.dataclass
class Evaluation:
    """The state the mocked activities share, standing in for the run's executions."""

    total: int
    scored: list[int] = dataclasses.field(default_factory=list)
    batches: list[int] = dataclasses.field(default_factory=list)
    # Offsets whose batch fails this many more times before it goes through.
    failures: dict[int, int] = dataclasses.field(default_factory=dict)
    opened: int = 0
    finished: int = 0
    failed: list[str] = dataclasses.field(default_factory=list)


def _activities(state: Evaluation):
    @activity.defn(name="open_run_evaluation")
    async def open_run_evaluation(run_id: str) -> int:
        state.opened += 1
        return state.total

    @activity.defn(name="evaluate_executions")
    async def evaluate_executions(run_id: str, offset: int, limit: int) -> int:
        state.batches.append(offset)
        if state.failures.get(offset, 0) > 0:
            state.failures[offset] -= 1
            raise ApplicationError("worker lost")
        page = list(range(offset, min(offset + limit, state.total)))
        for index in page:
            activity.heartbeat(index + 1)
        state.scored.extend(page)
        return len(page)

    @activity.defn(name="finish_run_evaluation")
    async def finish_run_evaluation(run_id: str) -> None:
        state.finished += 1

    @activity.defn(name="fail_run_evaluation")
    async def fail_run_evaluation(run_id: str, reason: str) -> None:
        state.failed.append(reason)

    return [
        open_run_evaluation,
        evaluate_executions,
        finish_run_evaluation,
        fail_run_evaluation,
    ]


@contextlib.asynccontextmanager
async def _environment(state: Evaluation):
    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue=TaskQueue.EXPERIMENTS.value,
            workflows=[EvaluateRunWorkflow],
            activities=_activities(state),
        ),
    ):
        yield env


async def _launch(env) -> dict:
    run_id = str(uuid.uuid4())
    return await env.client.execute_workflow(
        EvaluateRunWorkflow.run,
        EvaluateRunInput(run_id=run_id),
        id=f"evaluate-run-{run_id}-1",
        task_queue=TaskQueue.EXPERIMENTS.value,
    )


async def test_every_execution_is_scored_in_batches_then_aggregated() -> None:
    state = Evaluation(total=450)

    async with _environment(state) as env:
        result = await _launch(env)

    assert result["evaluated"] == 450
    assert state.batches == [0, 200, 400]
    assert state.scored == list(range(450))
    assert (state.opened, state.finished, state.failed) == (1, 1, [])


async def test_an_interrupted_batch_is_redone_and_the_done_ones_are_not() -> None:
    state = Evaluation(total=450, failures={200: 1})

    async with _environment(state) as env:
        await _launch(env)

    # The batch at 200 failed once and was retried; the one at 0 was never redone.
    assert state.batches == [0, 200, 200, 400]
    assert state.scored == list(range(450))
    assert state.finished == 1


async def test_a_run_with_nothing_to_score_still_aggregates() -> None:
    state = Evaluation(total=0)

    async with _environment(state) as env:
        result = await _launch(env)

    assert result["evaluated"] == 0
    assert state.finished == 1


async def test_a_failure_is_recorded_on_the_run() -> None:
    state = Evaluation(total=300, failures={200: 10})

    async with _environment(state) as env:
        with pytest.raises(WorkflowFailureError):
            await _launch(env)

    assert len(state.failed) == 1
    assert state.finished == 0
