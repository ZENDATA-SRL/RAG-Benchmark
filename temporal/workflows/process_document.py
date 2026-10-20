from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from temporal.activities.chunking import ChunkResultOutput, chunk_document
    from temporal.activities.parsing import ParseResult, parse_document
    from temporal.activities.reads import resolve_configuration
    from temporal.task_queues import TaskQueue

# Parsing a large PDF is slow but bounded; the timeout is generous yet finite, and the
# heartbeat timeout matches the per-page heartbeat of the parsing activity so a genuinely
# stuck parse is detected in seconds rather than after the whole start-to-close budget.
_PARSE_TIMEOUT = timedelta(minutes=30)
_PARSE_HEARTBEAT_TIMEOUT = timedelta(minutes=2)
_CHUNK_TIMEOUT = timedelta(minutes=15)
_READ_TIMEOUT = timedelta(seconds=30)

# A parse that failed permanently (corrupt/encrypted/scanned) never succeeds on retry; the
# activity records it and returns, but this makes the intent explicit for any path that
# raises instead of returning.
_RETRY_POLICY = RetryPolicy(
    non_retryable_error_types=["PermanentParsingError"],
)


@workflow.defn
class ProcessDocumentWorkflow:
    """Parse then chunk a single document under one chunking configuration.

    A permanently failed parse ends the workflow with a negative result instead of raising:
    a workflow that finished with `{status: "failed"}` is data the parent aggregates, not an
    anomaly that stops the run.
    """

    @workflow.run
    async def run(self, document_id: str, chunking_configuration_id: str) -> dict:
        configuration = await workflow.execute_activity(
            resolve_configuration,
            chunking_configuration_id,
            task_queue=TaskQueue.PARSING,
            start_to_close_timeout=_READ_TIMEOUT,
            retry_policy=_RETRY_POLICY,
        )

        parse: ParseResult = await workflow.execute_activity(
            parse_document,
            args=[document_id, configuration.parsing_profile_id],
            task_queue=TaskQueue.PARSING,
            start_to_close_timeout=_PARSE_TIMEOUT,
            heartbeat_timeout=_PARSE_HEARTBEAT_TIMEOUT,
            retry_policy=_RETRY_POLICY,
        )
        if parse.status != "ready":
            return {
                "status": "failed",
                "reason": "parse_failed",
                "document_id": document_id,
            }

        chunk: ChunkResultOutput = await workflow.execute_activity(
            chunk_document,
            args=[document_id, chunking_configuration_id, parse.parsing_result_id],
            task_queue=TaskQueue.CHUNKING,
            start_to_close_timeout=_CHUNK_TIMEOUT,
            retry_policy=_RETRY_POLICY,
        )
        return {
            "status": "ready",
            "document_id": document_id,
            "chunk_result_id": chunk.chunk_result_id,
            "chunk_count": chunk.chunk_count,
        }
