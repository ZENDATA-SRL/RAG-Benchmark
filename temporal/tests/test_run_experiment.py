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

from temporal.activities.experiments import ExperimentRunResolved
from temporal.task_queues import WORKER_TASK_QUEUES, TaskQueue
from temporal.workflows.run_experiment import (
    RunExperimentInput,
    RunExperimentWorkflow,
    RunVariantWorkflow,
)

pytestmark = pytest.mark.asyncio


@dataclasses.dataclass
class Run:
    """The state the mocked activities share, standing in for the `executions` table."""

    variant_ids: list[str]
    executions: dict[str, dict[str, str]]
    failing: set[str] = dataclasses.field(default_factory=set)
    attempts: dict[str, int] = dataclasses.field(default_factory=dict)
    listed_after: list[str | None] = dataclasses.field(default_factory=list)
    progress_records: int = 0
    finished: int = 0
    failed_runs: list[str] = dataclasses.field(default_factory=list)
    marked_failed: list[str] = dataclasses.field(default_factory=list)
    open_error: Exception | None = None


def _run(variants: int = 1, executions: int = 3) -> Run:
    variant_ids = [str(uuid.uuid4()) for _ in range(variants)]
    return Run(
        variant_ids=variant_ids,
        executions={
            variant_id: {str(uuid.uuid4()): "pending" for _ in range(executions)}
            for variant_id in variant_ids
        },
    )


def _activities(state: Run):
    @activity.defn(name="open_experiment_run")
    async def open_experiment_run(run_id: str) -> ExperimentRunResolved:
        if state.open_error is not None:
            raise state.open_error
        return ExperimentRunResolved(variant_ids=list(state.variant_ids))

    @activity.defn(name="list_unfinished_executions")
    async def list_unfinished_executions(
        run_id: str, variant_id: str, after_id: str | None, limit: int
    ) -> list[str]:
        state.listed_after.append(after_id)
        ids = sorted(
            key
            for key, status in state.executions[variant_id].items()
            if status != "succeeded" and (after_id is None or key > after_id)
        )
        return ids[:limit]

    @activity.defn(name="retrieve_question")
    async def retrieve_question(execution_id: str) -> str:
        state.attempts[execution_id] = state.attempts.get(execution_id, 0) + 1
        if execution_id in state.failing:
            raise ApplicationError("embedder is down")
        for executions in state.executions.values():
            if execution_id in executions:
                executions[execution_id] = "succeeded"
        return "succeeded"

    @activity.defn(name="mark_execution_failed")
    async def mark_execution_failed(execution_id: str, error: str) -> None:
        state.marked_failed.append(execution_id)
        for executions in state.executions.values():
            if execution_id in executions:
                executions[execution_id] = "failed"

    @activity.defn(name="record_run_progress")
    async def record_run_progress(run_id: str) -> None:
        state.progress_records += 1

    @activity.defn(name="finish_experiment_run")
    async def finish_experiment_run(run_id: str) -> None:
        state.finished += 1

    @activity.defn(name="fail_experiment_run")
    async def fail_experiment_run(run_id: str, reason: str) -> None:
        state.failed_runs.append(reason)

    return [
        open_experiment_run,
        list_unfinished_executions,
        retrieve_question,
        mark_execution_failed,
        record_run_progress,
        finish_experiment_run,
        fail_experiment_run,
    ]


@contextlib.asynccontextmanager
async def _environment(state: Run):
    async with await WorkflowEnvironment.start_time_skipping() as env:
        workers = [
            Worker(
                env.client,
                task_queue=queue.value,
                workflows=[RunExperimentWorkflow, RunVariantWorkflow],
                activities=_activities(state),
            )
            for queue in WORKER_TASK_QUEUES
        ]
        async with contextlib.AsyncExitStack() as stack:
            for worker in workers:
                await stack.enter_async_context(worker)
            yield env


async def _launch(env, run_id: str | None = None, concurrency: int = 5) -> dict:
    run_id = run_id or str(uuid.uuid4())
    return await env.client.execute_workflow(
        RunExperimentWorkflow.run,
        RunExperimentInput(run_id=run_id, concurrency=concurrency),
        id=f"run-experiment-{run_id}",
        task_queue=TaskQueue.EXPERIMENTS.value,
    )


async def test_every_execution_of_every_variant_is_retrieved() -> None:
    state = _run(variants=2, executions=3)

    async with _environment(state) as env:
        result = await _launch(env)

    assert [variant["processed"] for variant in result["variants"]] == [3, 3]
    assert all(
        status == "succeeded"
        for executions in state.executions.values()
        for status in executions.values()
    )
    assert state.finished == 1
    assert state.failed_runs == []


async def test_a_question_that_keeps_failing_does_not_stop_the_run() -> None:
    state = _run(executions=4)
    broken = sorted(next(iter(state.executions.values())))[1]
    state.failing.add(broken)

    async with _environment(state) as env:
        result = await _launch(env)

    statuses = next(iter(state.executions.values()))
    assert statuses[broken] == "failed"
    assert sum(status == "succeeded" for status in statuses.values()) == 3
    assert result["variants"][0]["failed"] == 1
    # Retried with backoff before giving up, then recorded, then the run still finished.
    assert state.attempts[broken] == 4
    assert state.marked_failed == [broken]
    assert state.finished == 1


async def test_a_relaunched_run_redoes_only_what_did_not_succeed() -> None:
    state = _run(executions=4)
    executions = next(iter(state.executions.values()))
    keys = sorted(executions)
    executions[keys[0]] = "succeeded"
    executions[keys[1]] = "succeeded"
    executions[keys[2]] = "failed"

    async with _environment(state) as env:
        await _launch(env)

    assert keys[0] not in state.attempts and keys[1] not in state.attempts
    assert state.attempts[keys[2]] == 1 and state.attempts[keys[3]] == 1
    assert set(executions.values()) == {"succeeded"}


async def test_a_large_variant_is_paged_and_continued_by_cursor() -> None:
    state = _run(executions=620)

    async with _environment(state) as env:
        result = await _launch(env, concurrency=20)

    assert result["variants"][0]["processed"] == 620
    assert len(state.attempts) == 620
    # Pages of 100, and the cursor of each is the last id of the previous page, never an
    # offset: executions leave the unfinished set as they succeed.
    assert state.listed_after[0] is None
    assert all(cursor is not None for cursor in state.listed_after[1:])
    assert state.progress_records == 7


async def test_a_failure_of_the_run_is_recorded_on_it() -> None:
    state = _run()
    state.open_error = ApplicationError("database gone", non_retryable=True)

    async with _environment(state) as env:
        with pytest.raises(WorkflowFailureError):
            await _launch(env)

    assert len(state.failed_runs) == 1
    assert state.finished == 0
