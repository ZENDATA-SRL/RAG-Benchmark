from __future__ import annotations

import asyncio
import dataclasses
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ChildWorkflowError

with workflow.unsafe.imports_passed_through():
    from src.infrastructure.temporal.workflow_ids import run_variant_workflow_id

    from temporal.activities.experiments import (
        fail_experiment_run,
        finish_experiment_run,
        list_unfinished_executions,
        mark_execution_failed,
        open_experiment_run,
        record_run_progress,
        retrieve_question,
    )
    from temporal.task_queues import TaskQueue

_DB_TIMEOUT = timedelta(seconds=60)
_FINISH_TIMEOUT = timedelta(minutes=10)
_RETRIEVE_TIMEOUT = timedelta(minutes=2)
_VARIANT_TIMEOUT = timedelta(hours=6)
_DB_RETRY = RetryPolicy(maximum_attempts=3)
# Backoff on the query itself: the embedder rate limits, and a transient failure that is
# retried at once fails again. Only errors raised by the activity are retried; a question
# the retrieval refuses is marked failed by the activity without raising.
_RETRIEVE_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=4,
)

_DEFAULT_CONCURRENCY = 5
_PAGE_SIZE = 100
# continue_as_new before the history grows unwieldy: an execution costs a handful of
# events, so five pages of a hundred keep one run of the workflow far from the limit.
_PAGES_PER_RUN = 5


@dataclasses.dataclass
class RunExperimentInput:
    """Arguments of a run: just ids and the concurrency."""

    run_id: str
    concurrency: int = _DEFAULT_CONCURRENCY


@dataclasses.dataclass
class RunVariantInput:
    """Arguments of one variant of a run, threaded through `continue_as_new` by cursor."""

    run_id: str
    variant_id: str
    concurrency: int = _DEFAULT_CONCURRENCY
    after_id: str | None = None
    processed: int = 0
    failed: int = 0


@workflow.defn
class RunVariantWorkflow:
    """Run every execution of one variant that has not succeeded yet.

    Pages through the unfinished executions with a cursor and runs each page with bounded
    concurrency. Executions that already succeeded are never listed, so a relaunched run
    redoes only the others: the execution row, unique per question, variant and
    repetition, is the unit of idempotency.
    """

    @workflow.run
    async def run(self, arg: RunVariantInput) -> dict:
        semaphore = asyncio.Semaphore(max(1, arg.concurrency))
        after_id = arg.after_id
        processed = arg.processed
        failed = arg.failed

        async def process(execution_id: str) -> str:
            async with semaphore:
                try:
                    return await workflow.execute_activity(
                        retrieve_question,
                        execution_id,
                        task_queue=TaskQueue.EXPERIMENTS,
                        start_to_close_timeout=_RETRIEVE_TIMEOUT,
                        retry_policy=_RETRIEVE_RETRY,
                    )
                except ActivityError as error:
                    # Retries exhausted: this question fails, the run does not.
                    await workflow.execute_activity(
                        mark_execution_failed,
                        args=[execution_id, str(error.cause or error)],
                        task_queue=TaskQueue.EXPERIMENTS,
                        start_to_close_timeout=_DB_TIMEOUT,
                        retry_policy=_DB_RETRY,
                    )
                    return "failed"

        for _ in range(_PAGES_PER_RUN):
            page = await workflow.execute_activity(
                list_unfinished_executions,
                args=[arg.run_id, arg.variant_id, after_id, _PAGE_SIZE],
                task_queue=TaskQueue.EXPERIMENTS,
                start_to_close_timeout=_DB_TIMEOUT,
                retry_policy=_DB_RETRY,
            )
            if not page:
                break
            statuses = await asyncio.gather(*(process(item) for item in page))
            processed += len(page)
            failed += sum(1 for status in statuses if status == "failed")
            after_id = page[-1]
            await workflow.execute_activity(
                record_run_progress,
                arg.run_id,
                task_queue=TaskQueue.EXPERIMENTS,
                start_to_close_timeout=_DB_TIMEOUT,
                retry_policy=_DB_RETRY,
            )
            if len(page) < _PAGE_SIZE:
                break
        else:
            workflow.continue_as_new(
                RunVariantInput(
                    run_id=arg.run_id,
                    variant_id=arg.variant_id,
                    concurrency=arg.concurrency,
                    after_id=after_id,
                    processed=processed,
                    failed=failed,
                )
            )
        return {"variant_id": arg.variant_id, "processed": processed, "failed": failed}


@workflow.defn
class RunExperimentWorkflow:
    """Run an experiment: one child workflow per variant, then score and aggregate.

    The variants run one after the other so that the run's concurrency is the number of
    queries in flight, whatever the number of variants: the query embeddings are rate
    limited. A question that fails never stops the run; a failure of the run itself is
    recorded on it, so it does not stay `running`.
    """

    @workflow.run
    async def run(self, arg: RunExperimentInput) -> dict:
        try:
            resolved = await workflow.execute_activity(
                open_experiment_run,
                arg.run_id,
                task_queue=TaskQueue.EXPERIMENTS,
                start_to_close_timeout=_DB_TIMEOUT,
                retry_policy=_DB_RETRY,
            )
            variants = []
            for variant_id in resolved.variant_ids:
                variants.append(
                    await workflow.execute_child_workflow(
                        RunVariantWorkflow.run,
                        RunVariantInput(
                            run_id=arg.run_id,
                            variant_id=variant_id,
                            concurrency=arg.concurrency,
                        ),
                        id=run_variant_workflow_id(arg.run_id, variant_id),
                        task_queue=TaskQueue.EXPERIMENTS,
                        execution_timeout=_VARIANT_TIMEOUT,
                    )
                )
            await workflow.execute_activity(
                finish_experiment_run,
                arg.run_id,
                task_queue=TaskQueue.EXPERIMENTS,
                start_to_close_timeout=_FINISH_TIMEOUT,
                retry_policy=_DB_RETRY,
            )
        except (ActivityError, ChildWorkflowError) as error:
            await workflow.execute_activity(
                fail_experiment_run,
                args=[arg.run_id, str(error.cause or error)],
                task_queue=TaskQueue.EXPERIMENTS,
                start_to_close_timeout=_DB_TIMEOUT,
                retry_policy=_DB_RETRY,
            )
            raise
        return {"run_id": arg.run_id, "variants": variants}
