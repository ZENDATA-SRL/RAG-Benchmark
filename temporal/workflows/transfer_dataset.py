from __future__ import annotations

import asyncio
import dataclasses
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from temporal.activities.transfer import (
        fail_transfer_job,
        finish_transfer_job,
        list_unranked_questions,
        mark_transfer_question_failed,
        open_transfer_job,
        rank_transfer_question,
        record_transfer_progress,
    )
    from temporal.task_queues import TaskQueue

_DB_TIMEOUT = timedelta(seconds=60)
# A question embeds its reference and every chunk of its gold documents in one call.
_RANK_TIMEOUT = timedelta(minutes=5)
_DB_RETRY = RetryPolicy(maximum_attempts=3)
# Backoff for the embedder, which rate limits; a question the ranking refuses is marked
# failed by the activity without raising, so only transient errors come back here.
_RANK_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=4,
)

_DEFAULT_CONCURRENCY = 4
_PAGE_SIZE = 50
# continue_as_new before the history grows unwieldy: a question costs a handful of events.
_PAGES_PER_RUN = 10


@dataclasses.dataclass
class TransferDatasetInput:
    """Arguments of a job, threaded through `continue_as_new` by cursor."""

    transfer_job_id: str
    concurrency: int = _DEFAULT_CONCURRENCY
    after_id: str | None = None
    opened: bool = False


@workflow.defn
class TransferDatasetWorkflow:
    """Rank the candidate chunks of every question of a transfer job.

    Pages through the questions not ranked yet with a cursor and ranks each page with
    bounded concurrency, since every question calls the embedder. A question is the unit
    of resume: one already ranked is never listed again, so a relaunched job picks up where
    the previous one stopped. A question that fails does not stop the job; a failure of
    the job itself is recorded on it before the workflow fails.
    """

    @workflow.run
    async def run(self, arg: TransferDatasetInput) -> dict:
        job_id = arg.transfer_job_id
        try:
            if not arg.opened:
                await workflow.execute_activity(
                    open_transfer_job,
                    job_id,
                    task_queue=TaskQueue.EXPERIMENTS,
                    start_to_close_timeout=_DB_TIMEOUT,
                    retry_policy=_DB_RETRY,
                )
            semaphore = asyncio.Semaphore(max(1, arg.concurrency))

            async def rank(question_id: str) -> str:
                async with semaphore:
                    try:
                        return await workflow.execute_activity(
                            rank_transfer_question,
                            question_id,
                            task_queue=TaskQueue.EXPERIMENTS,
                            start_to_close_timeout=_RANK_TIMEOUT,
                            retry_policy=_RANK_RETRY,
                        )
                    except ActivityError as error:
                        await workflow.execute_activity(
                            mark_transfer_question_failed,
                            args=[question_id, str(error.cause or error)],
                            task_queue=TaskQueue.EXPERIMENTS,
                            start_to_close_timeout=_DB_TIMEOUT,
                            retry_policy=_DB_RETRY,
                        )
                        return "failed"

            after_id = arg.after_id
            for _ in range(_PAGES_PER_RUN):
                page = await workflow.execute_activity(
                    list_unranked_questions,
                    args=[job_id, after_id, _PAGE_SIZE],
                    task_queue=TaskQueue.EXPERIMENTS,
                    start_to_close_timeout=_DB_TIMEOUT,
                    retry_policy=_DB_RETRY,
                )
                if not page:
                    break
                await asyncio.gather(*(rank(item) for item in page))
                after_id = page[-1]
                await workflow.execute_activity(
                    record_transfer_progress,
                    job_id,
                    task_queue=TaskQueue.EXPERIMENTS,
                    start_to_close_timeout=_DB_TIMEOUT,
                    retry_policy=_DB_RETRY,
                )
                if len(page) < _PAGE_SIZE:
                    break
            else:
                workflow.continue_as_new(
                    TransferDatasetInput(
                        transfer_job_id=job_id,
                        concurrency=arg.concurrency,
                        after_id=after_id,
                        opened=True,
                    )
                )
            await workflow.execute_activity(
                finish_transfer_job,
                job_id,
                task_queue=TaskQueue.EXPERIMENTS,
                start_to_close_timeout=_DB_TIMEOUT,
                retry_policy=_DB_RETRY,
            )
        except ActivityError as error:
            await workflow.execute_activity(
                fail_transfer_job,
                args=[job_id, str(error.cause or error)],
                task_queue=TaskQueue.EXPERIMENTS,
                start_to_close_timeout=_DB_TIMEOUT,
                retry_policy=_DB_RETRY,
            )
            raise
        return {"transfer_job_id": job_id}
