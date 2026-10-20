from __future__ import annotations

import asyncio
import dataclasses
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from temporal.activities.materialization import (
        documents_needing_chunking,
        open_materialization_run,
        record_progress,
        snapshot_documents_needing_chunking,
        summarize_run,
    )
    from temporal.task_queues import TaskQueue
    from temporal.workflow_ids import process_document_workflow_id
    from temporal.workflows.process_document import ProcessDocumentWorkflow

_ACTIVITY_TIMEOUT = timedelta(minutes=2)
_CHILD_TIMEOUT = timedelta(hours=1)
_RETRY_POLICY = RetryPolicy(maximum_attempts=3)

# continue_as_new before the history grows unwieldy (RT-O05). Conservative on purpose: a
# child completion adds several events, so a slice of 500 keeps a single run's history well
# within Temporal's limits while rarely triggering for real corpora.
_CONTINUE_AFTER = 500
_DEFAULT_CONCURRENCY = 5
# The failure list travels in the input on every continue_as_new, so it is capped to keep
# the payload bounded; the `failed` counter stays exact.
_MAX_REPORTED_FAILURES = 100


@dataclasses.dataclass
class MaterializeInput:
    """Arguments of a materialisation run.

    Either a **list of documents** or a **corpus snapshot**. The list serves a preview on
    one file (RF-P08) and small selections; the snapshot serves index builds, whose
    document set can be too large to travel in a payload, so the workflow pages it through
    `snapshot_offset` instead. `total` and the counters are carried across
    `continue_as_new` so the run's identity and reported progress survive the history
    reset.
    """

    document_ids: list[str]
    chunking_configuration_id: str
    corpus_id: str | None = None
    max_concurrency: int = _DEFAULT_CONCURRENCY
    total: int | None = None
    ready: int = 0
    failed: int = 0
    cached: int = 0
    failures: list[dict] = dataclasses.field(default_factory=list)
    corpus_snapshot_id: str | None = None
    snapshot_offset: int = 0


@workflow.defn
class MaterializeChunksWorkflow:
    """Materialise chunks for a set of documents, one child workflow per document.

    Idempotent by construction: the workflow id is deterministic in
    `(configuration, document set)`, so Temporal rejects a duplicate launch; a completed run
    relaunched finds every artefact in cache and finishes without doing parsing work.
    """

    @workflow.run
    async def run(self, arg: MaterializeInput) -> dict:
        workflow_id = workflow.info().workflow_id
        # `total` is the size of the original request; on continue_as_new it is threaded
        # through so the denominator the UI shows never shifts under it.
        total = arg.total if arg.total is not None else len(arg.document_ids)

        await workflow.execute_activity(
            open_materialization_run,
            args=[workflow_id, arg.chunking_configuration_id, total, arg.corpus_id],
            task_queue=TaskQueue.CHUNKING,
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
            retry_policy=_RETRY_POLICY,
        )

        next_offset: int | None = None
        if arg.corpus_snapshot_id is None:
            needing = await workflow.execute_activity(
                documents_needing_chunking,
                args=[arg.document_ids, arg.chunking_configuration_id],
                task_queue=TaskQueue.CHUNKING,
                start_to_close_timeout=_ACTIVITY_TIMEOUT,
                retry_policy=_RETRY_POLICY,
            )
            cached = arg.cached + (len(arg.document_ids) - len(needing))
            to_process = needing[:_CONTINUE_AFTER]
            remaining = needing[_CONTINUE_AFTER:]
        else:
            page = await workflow.execute_activity(
                snapshot_documents_needing_chunking,
                args=[
                    arg.corpus_snapshot_id,
                    arg.chunking_configuration_id,
                    arg.snapshot_offset,
                    _CONTINUE_AFTER,
                ],
                task_queue=TaskQueue.CHUNKING,
                start_to_close_timeout=_ACTIVITY_TIMEOUT,
                retry_policy=_RETRY_POLICY,
            )
            cached = arg.cached + (page.scanned - len(page.needing))
            to_process = page.needing
            remaining = []
            # A full page means there may be more; an empty next page ends the run.
            if page.scanned == _CONTINUE_AFTER:
                next_offset = arg.snapshot_offset + page.scanned

        ready = arg.ready
        failed = arg.failed
        failures = list(arg.failures)
        semaphore = asyncio.Semaphore(max(1, arg.max_concurrency))

        async def process(document_id: str) -> dict:
            # A bounded semaphore, not gather over everything: 200 documents must not launch
            # 200 concurrent children and saturate the worker.
            async with semaphore:
                return await workflow.execute_child_workflow(
                    ProcessDocumentWorkflow.run,
                    args=[document_id, arg.chunking_configuration_id],
                    id=process_document_workflow_id(
                        document_id, arg.chunking_configuration_id
                    ),
                    task_queue=TaskQueue.CHUNKING,
                    execution_timeout=_CHILD_TIMEOUT,
                )

        results = await asyncio.gather(
            *(process(document_id) for document_id in to_process)
        )
        for result in results:
            if result.get("status") == "ready":
                ready += 1
            else:
                failed += 1
                if len(failures) < _MAX_REPORTED_FAILURES:
                    failures.append(
                        {
                            "document_id": result.get("document_id"),
                            "error": result.get("reason"),
                        }
                    )

        progress = {"ready": ready, "failed": failed, "cached": cached}
        await workflow.execute_activity(
            record_progress,
            args=[workflow_id, progress],
            task_queue=TaskQueue.CHUNKING,
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
            retry_policy=_RETRY_POLICY,
        )

        if remaining or next_offset is not None:
            workflow.continue_as_new(
                MaterializeInput(
                    document_ids=remaining,
                    chunking_configuration_id=arg.chunking_configuration_id,
                    corpus_id=arg.corpus_id,
                    max_concurrency=arg.max_concurrency,
                    total=total,
                    ready=ready,
                    failed=failed,
                    cached=cached,
                    failures=failures,
                    corpus_snapshot_id=arg.corpus_snapshot_id,
                    snapshot_offset=next_offset or 0,
                )
            )

        await workflow.execute_activity(
            summarize_run,
            args=[workflow_id, progress],
            task_queue=TaskQueue.CHUNKING,
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
            retry_policy=_RETRY_POLICY,
        )
        return {
            "total": total,
            "ready": ready,
            "failed": failed,
            "skipped_cached": cached,
            "failures": failures,
        }
