from __future__ import annotations

import contextlib
import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from temporal.activities.chunking import ChunkResultOutput
from temporal.activities.parsing import ParseResult
from temporal.activities.reads import ConfigurationResolved
from temporal.task_queues import WORKER_TASK_QUEUES, TaskQueue
from temporal.workflows.process_document import ProcessDocumentWorkflow

pytestmark = pytest.mark.asyncio


def _configuration_id() -> str:
    return str(uuid.uuid4())


def _mock_activities(*, parse_status: str = "ready"):
    """Stand-ins for the DB/storage activities, so the workflow logic is tested in isolation."""

    @activity.defn(name="resolve_configuration")
    async def resolve_configuration(
        chunking_configuration_id: str,
    ) -> ConfigurationResolved:
        return ConfigurationResolved(
            parsing_profile_id=str(uuid.uuid4()),
            chunking_profile_id=str(uuid.uuid4()),
        )

    @activity.defn(name="parse_document")
    async def parse_document(document_id: str, parsing_profile_id: str) -> ParseResult:
        return ParseResult(parsing_result_id=str(uuid.uuid4()), status=parse_status)

    @activity.defn(name="chunk_document")
    async def chunk_document(
        document_id: str, chunking_configuration_id: str, parsing_result_id: str
    ) -> ChunkResultOutput:
        return ChunkResultOutput(chunk_result_id=str(uuid.uuid4()), chunk_count=7)

    return [resolve_configuration, parse_document, chunk_document]


@contextlib.asynccontextmanager
async def _workers(env: WorkflowEnvironment, activities, workflows):
    """Run a worker on every task queue, since the workflow pins activities per queue."""
    running = [
        Worker(
            env.client,
            task_queue=queue.value,
            workflows=workflows,
            activities=activities,
        )
        for queue in WORKER_TASK_QUEUES
    ]
    async with contextlib.AsyncExitStack() as stack:
        for worker in running:
            await stack.enter_async_context(worker)
        yield


async def test_happy_path_parses_then_chunks() -> None:
    async with await WorkflowEnvironment.start_time_skipping() as env:
        document_id = str(uuid.uuid4())
        config_id = _configuration_id()
        async with _workers(
            env, _mock_activities(parse_status="ready"), [ProcessDocumentWorkflow]
        ):
            result = await env.client.execute_workflow(
                ProcessDocumentWorkflow.run,
                args=[document_id, config_id],
                id=f"test-proc-{document_id}",
                task_queue=TaskQueue.PARSING.value,
            )
    assert result["status"] == "ready"
    assert result["chunk_count"] == 7


async def test_failed_parse_skips_chunking() -> None:
    async with await WorkflowEnvironment.start_time_skipping() as env:
        document_id = str(uuid.uuid4())
        config_id = _configuration_id()
        async with _workers(
            env, _mock_activities(parse_status="failed"), [ProcessDocumentWorkflow]
        ):
            result = await env.client.execute_workflow(
                ProcessDocumentWorkflow.run,
                args=[document_id, config_id],
                id=f"test-proc-{document_id}",
                task_queue=TaskQueue.PARSING.value,
            )
    assert result["status"] == "failed"
    assert result["reason"] == "parse_failed"
