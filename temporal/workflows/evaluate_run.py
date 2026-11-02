from __future__ import annotations

import dataclasses
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from temporal.activities.experiments import (
        evaluate_executions,
        fail_run_evaluation,
        finish_run_evaluation,
        open_run_evaluation,
    )
    from temporal.task_queues import TaskQueue

_DB_TIMEOUT = timedelta(seconds=60)
# A batch re-scores from stored hits, no embedder call: minutes are plenty, and the
# heartbeat notices a dead worker long before.
_BATCH_TIMEOUT = timedelta(minutes=10)
_BATCH_HEARTBEAT = timedelta(seconds=30)
_FINISH_TIMEOUT = timedelta(minutes=10)
_DB_RETRY = RetryPolicy(maximum_attempts=3)

_BATCH_SIZE = 200
# continue_as_new before the history grows unwieldy: a batch costs a handful of events.
_BATCHES_PER_RUN = 50


@dataclasses.dataclass
class EvaluateRunInput:
    """Arguments of a re-evaluation, threaded through `continue_as_new` by offset."""

    run_id: str
    offset: int = 0
    opened: bool = False


@workflow.defn
class EvaluateRunWorkflow:
    """Re-score every execution of a finished run in batches, then aggregate.

    Nothing is retrieved again: each execution is scored from the hits it recorded, on the
    evidence as it is now. A batch is the unit of resume: the batches already done are in
    the history, so a re-evaluation interrupted by a worker restart carries on from the
    batch it was in. A failure is recorded on the run before the workflow fails, so the
    run does not stay "being re-evaluated".
    """

    @workflow.run
    async def run(self, arg: EvaluateRunInput) -> dict:
        offset = arg.offset
        try:
            if not arg.opened:
                await workflow.execute_activity(
                    open_run_evaluation,
                    arg.run_id,
                    task_queue=TaskQueue.EXPERIMENTS,
                    start_to_close_timeout=_DB_TIMEOUT,
                    retry_policy=_DB_RETRY,
                )
            for _ in range(_BATCHES_PER_RUN):
                scored = await workflow.execute_activity(
                    evaluate_executions,
                    args=[arg.run_id, offset, _BATCH_SIZE],
                    task_queue=TaskQueue.EXPERIMENTS,
                    start_to_close_timeout=_BATCH_TIMEOUT,
                    heartbeat_timeout=_BATCH_HEARTBEAT,
                    retry_policy=_DB_RETRY,
                )
                offset += scored
                if scored < _BATCH_SIZE:
                    break
            else:
                workflow.continue_as_new(
                    EvaluateRunInput(run_id=arg.run_id, offset=offset, opened=True)
                )
            await workflow.execute_activity(
                finish_run_evaluation,
                arg.run_id,
                task_queue=TaskQueue.EXPERIMENTS,
                start_to_close_timeout=_FINISH_TIMEOUT,
                retry_policy=_DB_RETRY,
            )
        except ActivityError as error:
            await workflow.execute_activity(
                fail_run_evaluation,
                args=[arg.run_id, str(error.cause or error)],
                task_queue=TaskQueue.EXPERIMENTS,
                start_to_close_timeout=_DB_TIMEOUT,
                retry_policy=_DB_RETRY,
            )
            raise
        return {"run_id": arg.run_id, "evaluated": offset}
