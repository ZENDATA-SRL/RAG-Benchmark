from __future__ import annotations

import asyncio
import dataclasses
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from temporal.activities.generation import (
        GenerationUnitRef,
        fail_generation_job,
        finish_generation_job,
        list_generation_units,
        mark_generation_unit_failed,
        open_generation_job,
        record_generation_progress,
        run_generation_unit,
    )
    from temporal.task_queues import TaskQueue

_DB_TIMEOUT = timedelta(seconds=60)
# A unit is an agent reading and submitting for many model calls.
_UNIT_TIMEOUT = timedelta(minutes=15)
# Every tool call heartbeats, and no single model call takes this long.
_UNIT_HEARTBEAT = timedelta(minutes=3)
_DB_RETRY = RetryPolicy(maximum_attempts=3)
# Same backoff as the answers of a Q&A run: a chat model rate limits for long. A unit the
# model cannot complete ends with what it saved, so only provider failures come back here.
_UNIT_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=5),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=60),
    maximum_attempts=5,
)

_DOCUMENT = "document"
_CROSS = "cross"
_DEFAULT_CONCURRENCY = 4
_PAGE_SIZE = 20
# continue_as_new before the history grows unwieldy: a unit costs a handful of events.
_PAGES_PER_RUN = 10


@dataclasses.dataclass
class GenerateQuestionsInput:
    """Arguments of a job, threaded through `continue_as_new` by phase and cursor."""

    generation_job_id: str
    concurrency: int = _DEFAULT_CONCURRENCY
    phase: str = _DOCUMENT
    after_position: int | None = None
    opened: bool = False


@workflow.defn
class GenerateQuestionsWorkflow:
    """Generate the questions of a job: one unit per document, then the cross units.

    The document units run with bounded concurrency, since each calls the chat model. The
    cross units start when the document phase is over, because they read the summaries it
    left, and run one at a time, each seeing what the previous ones delivered. A unit is
    the unit of resume: one that succeeded is never listed again, so a relaunched job picks
    up where the previous one stopped. A unit that fails does not stop the job; a failure
    of the job itself is recorded on it before the workflow fails.
    """

    @workflow.run
    async def run(self, arg: GenerateQuestionsInput) -> dict:
        job_id = arg.generation_job_id
        try:
            if not arg.opened:
                ready = await workflow.execute_activity(
                    open_generation_job,
                    job_id,
                    task_queue=TaskQueue.EXPERIMENTS,
                    start_to_close_timeout=_DB_TIMEOUT,
                    retry_policy=_DB_RETRY,
                )
                if not ready:
                    return {"generation_job_id": job_id, "ran": False}
            phase = arg.phase
            after = arg.after_position
            for _ in range(_PAGES_PER_RUN):
                page = await workflow.execute_activity(
                    list_generation_units,
                    args=[job_id, phase, after, _PAGE_SIZE],
                    task_queue=TaskQueue.EXPERIMENTS,
                    start_to_close_timeout=_DB_TIMEOUT,
                    retry_policy=_DB_RETRY,
                    result_type=list[GenerationUnitRef],
                )
                if page:
                    await self._run_page(job_id, phase, page, arg.concurrency)
                    after = page[-1].position
                    await workflow.execute_activity(
                        record_generation_progress,
                        job_id,
                        task_queue=TaskQueue.EXPERIMENTS,
                        start_to_close_timeout=_DB_TIMEOUT,
                        retry_policy=_DB_RETRY,
                    )
                if len(page) < _PAGE_SIZE:
                    if phase == _CROSS:
                        break
                    phase, after = _CROSS, None
            else:
                workflow.continue_as_new(
                    GenerateQuestionsInput(
                        generation_job_id=job_id,
                        concurrency=arg.concurrency,
                        phase=phase,
                        after_position=after,
                        opened=True,
                    )
                )
            await workflow.execute_activity(
                finish_generation_job,
                job_id,
                task_queue=TaskQueue.EXPERIMENTS,
                start_to_close_timeout=_DB_TIMEOUT,
                retry_policy=_DB_RETRY,
            )
        except ActivityError as error:
            await workflow.execute_activity(
                fail_generation_job,
                args=[job_id, str(error.cause or error)],
                task_queue=TaskQueue.EXPERIMENTS,
                start_to_close_timeout=_DB_TIMEOUT,
                retry_policy=_DB_RETRY,
            )
            raise
        return {"generation_job_id": job_id, "ran": True}

    async def _run_page(
        self,
        job_id: str,
        phase: str,
        page: list[GenerationUnitRef],
        concurrency: int,
    ) -> None:
        # The cross units read what the previous ones delivered, so they go in order.
        limit = max(1, concurrency) if phase == _DOCUMENT else 1
        semaphore = asyncio.Semaphore(limit)

        async def run(unit: GenerationUnitRef) -> str:
            async with semaphore:
                try:
                    return await workflow.execute_activity(
                        run_generation_unit,
                        unit.unit_id,
                        task_queue=TaskQueue.LLM,
                        start_to_close_timeout=_UNIT_TIMEOUT,
                        heartbeat_timeout=_UNIT_HEARTBEAT,
                        retry_policy=_UNIT_RETRY,
                    )
                except ActivityError as error:
                    await workflow.execute_activity(
                        mark_generation_unit_failed,
                        args=[unit.unit_id, str(error.cause or error)],
                        task_queue=TaskQueue.EXPERIMENTS,
                        start_to_close_timeout=_DB_TIMEOUT,
                        retry_policy=_DB_RETRY,
                    )
                    return "failed"

        if limit == 1:
            for unit in page:
                await run(unit)
        else:
            await asyncio.gather(*(run(unit) for unit in page))
