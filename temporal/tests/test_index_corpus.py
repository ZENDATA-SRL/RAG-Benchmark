from __future__ import annotations

import contextlib
import dataclasses
import uuid

import pytest
from src.infrastructure.temporal.codec import SizeGuardCodec
from temporalio import activity
from temporalio.client import WorkflowFailureError
from temporalio.converter import default as default_converter
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from temporal.activities.chunking import ChunkResultOutput
from temporal.activities.embed import EmbedBatchOutput
from temporal.activities.indexing import IndexBuildResolved
from temporal.activities.materialization import SnapshotDocumentsPage
from temporal.activities.parsing import ParseResult
from temporal.activities.reads import ConfigurationResolved
from temporal.task_queues import WORKER_TASK_QUEUES, TaskQueue
from temporal.workflows.index_corpus import IndexCorpusWorkflow
from temporal.workflows.materialize_chunks import (
    MaterializeChunksWorkflow,
    MaterializeInput,
)
from temporal.workflows.process_document import ProcessDocumentWorkflow

pytestmark = pytest.mark.asyncio

# A quarter of the real 128 KB, so a test proves the paging rather than the corpus size:
# the 1200 document ids of the paging test would exceed it if passed as a list, while one
# page of 500 fits.
_TIGHT_LIMIT = 32 * 1024


@dataclasses.dataclass
class Calls:
    """What the mocked activities saw, for the assertions."""

    snapshot_offsets: list[int] = dataclasses.field(default_factory=list)
    embedded_offsets: list[int] = dataclasses.field(default_factory=list)
    upserted_offsets: list[int] = dataclasses.field(default_factory=list)
    collections_prepared: int = 0
    completed: list[bool] = dataclasses.field(default_factory=list)


def _activities(
    calls: Calls,
    *,
    document_ids: list[str],
    total_chunks: int,
    embed_error: Exception | None = None,
):
    """Mocks over every DB, storage, embedder and vector store activity."""

    @activity.defn(name="resolve_configuration")
    async def resolve_configuration(
        chunking_configuration_id: str,
    ) -> ConfigurationResolved:
        return ConfigurationResolved(
            parsing_profile_id=str(uuid.uuid4()), chunking_profile_id=str(uuid.uuid4())
        )

    @activity.defn(name="parse_document")
    async def parse_document(document_id: str, parsing_profile_id: str) -> ParseResult:
        return ParseResult(parsing_result_id=str(uuid.uuid4()), status="ready")

    @activity.defn(name="chunk_document")
    async def chunk_document(
        document_id: str, chunking_configuration_id: str, parsing_result_id: str
    ) -> ChunkResultOutput:
        return ChunkResultOutput(chunk_result_id=str(uuid.uuid4()), chunk_count=1)

    @activity.defn(name="open_materialization_run")
    async def open_materialization_run(
        workflow_id: str, chunking_configuration_id: str, document_count: int, corpus_id
    ) -> str:
        return str(uuid.uuid4())

    @activity.defn(name="documents_needing_chunking")
    async def documents_needing_chunking(
        document_ids: list[str], chunking_configuration_id: str
    ) -> list[str]:
        return list(document_ids)

    @activity.defn(name="snapshot_documents_needing_chunking")
    async def snapshot_documents_needing_chunking(
        corpus_snapshot_id: str, chunking_configuration_id: str, offset: int, limit: int
    ) -> SnapshotDocumentsPage:
        calls.snapshot_offsets.append(offset)
        page = document_ids[offset : offset + limit]
        return SnapshotDocumentsPage(scanned=len(page), needing=page)

    @activity.defn(name="record_progress")
    async def record_progress(workflow_id: str, progress: dict) -> None:
        return None

    @activity.defn(name="summarize_run")
    async def summarize_run(workflow_id: str, progress: dict) -> None:
        return None

    @activity.defn(name="resolve_index_build")
    async def resolve_index_build(index_build_id: str) -> IndexBuildResolved:
        return IndexBuildResolved(
            index_build_id=index_build_id,
            corpus_snapshot_id=str(uuid.uuid4()),
            chunking_configuration_id=str(uuid.uuid4()),
            embedding_profile_id=str(uuid.uuid4()),
            composition_hash="0" * 64,
            document_count=len(document_ids),
        )

    @activity.defn(name="open_index_build")
    async def open_index_build(workflow_id: str, index_build_id: str) -> None:
        return None

    @activity.defn(name="complete_index_build")
    async def complete_index_build(workflow_id: str, failed: bool = False) -> None:
        calls.completed.append(failed)

    @activity.defn(name="count_index_chunks")
    async def count_index_chunks(index_build_id: str) -> int:
        return total_chunks

    @activity.defn(name="prepare_index_collection")
    async def prepare_index_collection(index_build_id: str) -> None:
        calls.collections_prepared += 1

    @activity.defn(name="embed_batch")
    async def embed_batch(
        index_build_id: str, embedding_profile_id: str, batch_offset: int, limit: int
    ) -> EmbedBatchOutput:
        if embed_error is not None:
            raise embed_error
        count = max(0, min(limit, total_chunks - batch_offset))
        if count:
            calls.embedded_offsets.append(batch_offset)
        return EmbedBatchOutput(embedded_count=count, output_uri="s3://b/k")

    @activity.defn(name="upsert_embedding_batch")
    async def upsert_embedding_batch(index_build_id: str, batch_offset: int) -> int:
        calls.upserted_offsets.append(batch_offset)
        return min(100, total_chunks - batch_offset)

    return [
        resolve_configuration,
        parse_document,
        chunk_document,
        open_materialization_run,
        documents_needing_chunking,
        snapshot_documents_needing_chunking,
        record_progress,
        summarize_run,
        resolve_index_build,
        open_index_build,
        complete_index_build,
        count_index_chunks,
        prepare_index_collection,
        embed_batch,
        upsert_embedding_batch,
    ]


@contextlib.asynccontextmanager
async def _environment(activities):
    """Time-skipping server and workers, with the size guard tightened."""
    converter = dataclasses.replace(
        default_converter(), payload_codec=SizeGuardCodec(limit=_TIGHT_LIMIT)
    )
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=converter
    ) as env:
        workers = [
            Worker(
                env.client,
                task_queue=queue.value,
                workflows=[
                    IndexCorpusWorkflow,
                    MaterializeChunksWorkflow,
                    ProcessDocumentWorkflow,
                ],
                activities=activities,
            )
            for queue in WORKER_TASK_QUEUES
        ]
        async with contextlib.AsyncExitStack() as stack:
            for worker in workers:
                await stack.enter_async_context(worker)
            yield env


async def test_index_build_embeds_and_upserts_every_batch() -> None:
    calls = Calls()
    activities = _activities(
        calls, document_ids=[str(uuid.uuid4()) for _ in range(3)], total_chunks=250
    )

    async with _environment(activities) as env:
        result = await env.client.execute_workflow(
            IndexCorpusWorkflow.run,
            str(uuid.uuid4()),
            id=f"index-corpus-{uuid.uuid4()}",
            task_queue=TaskQueue.CHUNKING.value,
        )

    assert result["status"] == "ready"
    assert result["embedded"] == 250
    assert result["upserted"] == 250
    assert calls.collections_prepared == 1
    assert calls.embedded_offsets == calls.upserted_offsets == [0, 100, 200]
    assert calls.completed == [False]


async def test_snapshot_larger_than_the_payload_limit_is_paged() -> None:
    """The document ids never travel in a payload, so the size of the snapshot is free."""
    calls = Calls()
    document_ids = [str(uuid.uuid4()) for _ in range(1200)]
    activities = _activities(calls, document_ids=document_ids, total_chunks=0)

    async with _environment(activities) as env:
        result = await env.client.execute_workflow(
            IndexCorpusWorkflow.run,
            str(uuid.uuid4()),
            id=f"index-corpus-{uuid.uuid4()}",
            task_queue=TaskQueue.CHUNKING.value,
        )

    assert result["status"] == "ready"
    assert calls.snapshot_offsets == [0, 500, 1000]
    assert calls.completed == [False]


async def test_materialisation_by_snapshot_counts_every_document() -> None:
    calls = Calls()
    document_ids = [str(uuid.uuid4()) for _ in range(1000)]
    activities = _activities(calls, document_ids=document_ids, total_chunks=0)

    async with _environment(activities) as env:
        result = await env.client.execute_workflow(
            MaterializeChunksWorkflow.run,
            MaterializeInput(
                document_ids=[],
                chunking_configuration_id=str(uuid.uuid4()),
                corpus_snapshot_id=str(uuid.uuid4()),
                total=len(document_ids),
            ),
            id=f"materialize-{uuid.uuid4()}",
            task_queue=TaskQueue.CHUNKING.value,
        )

    # 1000 is a multiple of the page size: the last, empty page ends the run.
    assert calls.snapshot_offsets == [0, 500, 1000]
    assert result["total"] == 1000
    assert result["ready"] == 1000


async def test_permanent_embedding_failure_marks_the_build_failed() -> None:
    calls = Calls()
    activities = _activities(
        calls,
        document_ids=[str(uuid.uuid4())],
        total_chunks=10,
        embed_error=ApplicationError(
            "wrong dimensions", type="EmbeddingDimensionMismatch", non_retryable=True
        ),
    )

    async with _environment(activities) as env:
        with pytest.raises(WorkflowFailureError):
            await env.client.execute_workflow(
                IndexCorpusWorkflow.run,
                str(uuid.uuid4()),
                id=f"index-corpus-{uuid.uuid4()}",
                task_queue=TaskQueue.CHUNKING.value,
            )

    assert calls.upserted_offsets == []
    assert calls.completed == [True]
