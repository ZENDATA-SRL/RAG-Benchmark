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
from temporal.workflows.materialize_chunks import MaterializeChunksWorkflow, MaterializeInput
from temporal.workflows.process_document import ProcessDocumentWorkflow

pytestmark = pytest.mark.asyncio


def _mock_activities(*, failing: set[str], needing: list[str] | None):
    """Mocks over the DB/storage activities.

    `failing` are the document ids whose parse fails; `needing` overrides what
    `documents_needing_chunking` returns (None means "all of them", i.e. nothing cached).
    """
    progress_writes: list[dict] = []

    @activity.defn(name="resolve_configuration")
    async def resolve_configuration(chunking_configuration_id: str) -> ConfigurationResolved:
        return ConfigurationResolved(
            parsing_profile_id=str(uuid.uuid4()),
            chunking_profile_id=str(uuid.uuid4()),
        )

    @activity.defn(name="parse_document")
    async def parse_document(document_id: str, parsing_profile_id: str) -> ParseResult:
        status = "failed" if document_id in failing else "ready"
        return ParseResult(parsing_result_id=str(uuid.uuid4()), status=status)

    @activity.defn(name="chunk_document")
    async def chunk_document(
        document_id: str, chunking_configuration_id: str, parsing_result_id: str
    ) -> ChunkResultOutput:
        return ChunkResultOutput(chunk_result_id=str(uuid.uuid4()), chunk_count=3)

    @activity.defn(name="open_materialization_run")
    async def open_materialization_run(
        workflow_id: str, chunking_configuration_id: str, document_count: int, corpus_id
    ) -> str:
        return str(uuid.uuid4())

    @activity.defn(name="documents_needing_chunking")
    async def documents_needing_chunking(
        document_ids: list[str], chunking_configuration_id: str
    ) -> list[str]:
        return list(document_ids) if needing is None else list(needing)

    @activity.defn(name="record_progress")
    async def record_progress(workflow_id: str, progress: dict) -> None:
        progress_writes.append(dict(progress))

    @activity.defn(name="summarize_run")
    async def summarize_run(workflow_id: str, progress: dict) -> None:
        return None

    activities = [
        resolve_configuration,
        parse_document,
        chunk_document,
        open_materialization_run,
        documents_needing_chunking,
        record_progress,
        summarize_run,
    ]
    return activities, progress_writes


@contextlib.asynccontextmanager
async def _workers(env: WorkflowEnvironment, activities):
    running = [
        Worker(
            env.client,
            task_queue=queue.value,
            workflows=[MaterializeChunksWorkflow, ProcessDocumentWorkflow],
            activities=activities,
        )
        for queue in WORKER_TASK_QUEUES
    ]
    async with contextlib.AsyncExitStack() as stack:
        for worker in running:
            await stack.enter_async_context(worker)
        yield


async def test_one_failed_document_does_not_block_the_others() -> None:
    document_ids = [str(uuid.uuid4()) for _ in range(10)]
    failing = {document_ids[0]}
    activities, _ = _mock_activities(failing=failing, needing=None)

    async with await WorkflowEnvironment.start_time_skipping() as env:
        config_id = str(uuid.uuid4())
        async with _workers(env, activities):
            result = await env.client.execute_workflow(
                MaterializeChunksWorkflow.run,
                MaterializeInput(
                    document_ids=document_ids, chunking_configuration_id=config_id
                ),
                id=f"materialize-{config_id}",
                task_queue=TaskQueue.CHUNKING.value,
            )

    assert result["total"] == 10
    assert result["ready"] == 9
    assert result["failed"] == 1
    assert len(result["failures"]) == 1


async def test_second_launch_finds_everything_cached() -> None:
    """When nothing needs chunking, the run completes without any child work."""
    document_ids = [str(uuid.uuid4()) for _ in range(5)]
    activities, _ = _mock_activities(failing=set(), needing=[])

    async with await WorkflowEnvironment.start_time_skipping() as env:
        config_id = str(uuid.uuid4())
        async with _workers(env, activities):
            result = await env.client.execute_workflow(
                MaterializeChunksWorkflow.run,
                MaterializeInput(
                    document_ids=document_ids, chunking_configuration_id=config_id
                ),
                id=f"materialize-{config_id}",
                task_queue=TaskQueue.CHUNKING.value,
            )

    assert result["total"] == 5
    assert result["ready"] == 0
    assert result["failed"] == 0
    assert result["skipped_cached"] == 5
