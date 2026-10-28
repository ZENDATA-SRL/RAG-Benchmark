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

from temporal.task_queues import WORKER_TASK_QUEUES, TaskQueue
from temporal.workflows.transfer_dataset import (
    TransferDatasetInput,
    TransferDatasetWorkflow,
)

pytestmark = pytest.mark.asyncio


@dataclasses.dataclass
class Job:
    """The state the mocked activities share, standing in for `transfer_questions`."""

    questions: dict[str, str]
    failing: set[str] = dataclasses.field(default_factory=set)
    attempts: dict[str, int] = dataclasses.field(default_factory=dict)
    listed_after: list[str | None] = dataclasses.field(default_factory=list)
    opened: int = 0
    progress_records: int = 0
    finished: int = 0
    failed_jobs: list[str] = dataclasses.field(default_factory=list)
    marked_failed: list[str] = dataclasses.field(default_factory=list)
    open_error: Exception | None = None


def _job(questions: int = 3) -> Job:
    return Job(questions={str(uuid.uuid4()): "pending" for _ in range(questions)})


def _activities(state: Job):
    @activity.defn(name="open_transfer_job")
    async def open_transfer_job(transfer_job_id: str) -> None:
        if state.open_error is not None:
            raise state.open_error
        state.opened += 1

    @activity.defn(name="list_unranked_questions")
    async def list_unranked_questions(
        transfer_job_id: str, after_id: str | None, limit: int
    ) -> list[str]:
        state.listed_after.append(after_id)
        ids = sorted(
            key
            for key, status in state.questions.items()
            if status != "succeeded" and (after_id is None or key > after_id)
        )
        return ids[:limit]

    @activity.defn(name="rank_transfer_question")
    async def rank_transfer_question(transfer_question_id: str) -> str:
        state.attempts[transfer_question_id] = (
            state.attempts.get(transfer_question_id, 0) + 1
        )
        if transfer_question_id in state.failing:
            raise ApplicationError("embedder is down")
        state.questions[transfer_question_id] = "succeeded"
        return "succeeded"

    @activity.defn(name="mark_transfer_question_failed")
    async def mark_transfer_question_failed(
        transfer_question_id: str, error: str
    ) -> None:
        state.marked_failed.append(transfer_question_id)
        state.questions[transfer_question_id] = "failed"

    @activity.defn(name="record_transfer_progress")
    async def record_transfer_progress(transfer_job_id: str) -> None:
        state.progress_records += 1

    @activity.defn(name="finish_transfer_job")
    async def finish_transfer_job(transfer_job_id: str) -> None:
        state.finished += 1

    @activity.defn(name="fail_transfer_job")
    async def fail_transfer_job(transfer_job_id: str, reason: str) -> None:
        state.failed_jobs.append(reason)

    return [
        open_transfer_job,
        list_unranked_questions,
        rank_transfer_question,
        mark_transfer_question_failed,
        record_transfer_progress,
        finish_transfer_job,
        fail_transfer_job,
    ]


@contextlib.asynccontextmanager
async def _environment(state: Job):
    async with await WorkflowEnvironment.start_time_skipping() as env:
        workers = [
            Worker(
                env.client,
                task_queue=queue.value,
                workflows=[TransferDatasetWorkflow],
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
        TransferDatasetWorkflow.run,
        TransferDatasetInput(transfer_job_id=job_id, concurrency=concurrency),
        id=f"transfer-dataset-{job_id}",
        task_queue=TaskQueue.EXPERIMENTS.value,
    )


async def test_every_question_is_ranked_then_the_job_closes() -> None:
    state = _job(questions=3)

    async with _environment(state) as env:
        await _launch(env)

    assert set(state.questions.values()) == {"succeeded"}
    assert (state.opened, state.finished, state.failed_jobs) == (1, 1, [])


async def test_a_question_that_keeps_failing_does_not_stop_the_job() -> None:
    state = _job(questions=4)
    broken = sorted(state.questions)[1]
    state.failing.add(broken)

    async with _environment(state) as env:
        await _launch(env)

    assert state.questions[broken] == "failed"
    assert state.attempts[broken] == 4
    assert state.marked_failed == [broken]
    assert sum(status == "succeeded" for status in state.questions.values()) == 3
    assert state.finished == 1


async def test_a_resumed_job_ranks_only_the_questions_left() -> None:
    state = _job(questions=4)
    keys = sorted(state.questions)
    state.questions[keys[0]] = "succeeded"
    state.questions[keys[1]] = "succeeded"

    async with _environment(state) as env:
        await _launch(env)

    assert set(state.attempts) == {keys[2], keys[3]}


async def test_a_large_job_is_paged_and_continued_by_cursor() -> None:
    state = _job(questions=620)

    async with _environment(state) as env:
        await _launch(env, concurrency=20)

    assert len(state.attempts) == 620
    assert state.listed_after[0] is None
    assert all(cursor is not None for cursor in state.listed_after[1:])
    # Opened once, although the history was continued as new after ten pages.
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
