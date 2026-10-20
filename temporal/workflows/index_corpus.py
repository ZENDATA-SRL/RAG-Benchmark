from __future__ import annotations

import dataclasses
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    import uuid

    from src.pipelines.workflow_ids import materialize_workflow_id

    from temporal.activities.embed import embed_batch
    from temporal.activities.indexing import (
        complete_index_build,
        count_index_chunks,
        fetch_index_chunk_batch,
        open_index_build,
        resolve_index_build,
    )
    from temporal.task_queues import TaskQueue
    from temporal.workflows.materialize_chunks import (
        MaterializeChunksWorkflow,
        MaterializeInput,
    )

_READ_TIMEOUT = timedelta(seconds=30)
_MATERIALIZE_TIMEOUT = timedelta(hours=2)
_EMBED_TIMEOUT = timedelta(minutes=15)
_RETRY_POLICY = RetryPolicy(maximum_attempts=3)
_EMBED_BATCH_SIZE = 100
# continue_as_new before embedding history grows too large (RT-O05).
_CONTINUE_AFTER_BATCHES = 100


@dataclasses.dataclass
class IndexCorpusInput:
    """Arguments of an index build run, threaded through `continue_as_new`."""

    index_build_id: str
    chunking_configuration_id: str | None = None
    embedding_profile_id: str | None = None
    document_ids: list[str] | None = None
    chunks_materialized: bool = False
    chunk_offset: int = 0
    total_chunks: int | None = None
    embedded: int = 0
    embedding_uris: list[str] = dataclasses.field(default_factory=list)


@workflow.defn
class IndexCorpusWorkflow:
    """Materialise chunks for a snapshot, embed them, and stop before the vector store.

    Matches the first half of `BuildIndexWorkflow` from the requirements: chunk
    materialisation via the existing child workflow, then batched embedding to object
    storage. Upsert into the vector DB is intentionally omitted for now.
    """

    @workflow.run
    async def run(self, arg: IndexCorpusInput | str) -> dict:
        if isinstance(arg, str):
            arg = IndexCorpusInput(index_build_id=arg)

        workflow_id = workflow.info().workflow_id

        if not arg.chunks_materialized:
            build = await workflow.execute_activity(
                resolve_index_build,
                arg.index_build_id,
                task_queue=TaskQueue.CHUNKING,
                start_to_close_timeout=_READ_TIMEOUT,
                retry_policy=_RETRY_POLICY,
            )
            await workflow.execute_activity(
                open_index_build,
                args=[workflow_id, arg.index_build_id],
                task_queue=TaskQueue.CHUNKING,
                start_to_close_timeout=_READ_TIMEOUT,
                retry_policy=_RETRY_POLICY,
            )

            materialize = await workflow.execute_child_workflow(
                MaterializeChunksWorkflow.run,
                MaterializeInput(
                    document_ids=build.document_ids,
                    chunking_configuration_id=build.chunking_configuration_id,
                ),
                id=materialize_workflow_id(
                    uuid.UUID(build.chunking_configuration_id),
                    [uuid.UUID(document_id) for document_id in build.document_ids],
                ),
                task_queue=TaskQueue.CHUNKING,
                execution_timeout=_MATERIALIZE_TIMEOUT,
            )
            if materialize.get("failed", 0) > 0:
                await workflow.execute_activity(
                    complete_index_build,
                    args=[workflow_id, True],
                    task_queue=TaskQueue.CHUNKING,
                    start_to_close_timeout=_READ_TIMEOUT,
                    retry_policy=_RETRY_POLICY,
                )
                return {
                    "status": "failed",
                    "reason": "chunk_materialization_failed",
                    "materialize": materialize,
                }

            total_chunks = await workflow.execute_activity(
                count_index_chunks,
                arg.index_build_id,
                task_queue=TaskQueue.CHUNKING,
                start_to_close_timeout=_READ_TIMEOUT,
                retry_policy=_RETRY_POLICY,
            )
            arg = IndexCorpusInput(
                index_build_id=arg.index_build_id,
                chunking_configuration_id=build.chunking_configuration_id,
                embedding_profile_id=build.embedding_profile_id,
                document_ids=build.document_ids,
                chunks_materialized=True,
                total_chunks=total_chunks,
            )

        total_chunks = arg.total_chunks or 0
        embedding_profile_id = arg.embedding_profile_id
        assert embedding_profile_id is not None

        offset = arg.chunk_offset
        embedded = arg.embedded
        embedding_uris = list(arg.embedding_uris)
        batches_done = 0

        while offset < total_chunks and batches_done < _CONTINUE_AFTER_BATCHES:
            batch = await workflow.execute_activity(
                fetch_index_chunk_batch,
                args=[arg.index_build_id, offset, _EMBED_BATCH_SIZE],
                task_queue=TaskQueue.CHUNKING,
                start_to_close_timeout=_READ_TIMEOUT,
                retry_policy=_RETRY_POLICY,
            )
            if not batch.chunks:
                break

            result = await workflow.execute_activity(
                embed_batch,
                args=[
                    arg.index_build_id,
                    embedding_profile_id,
                    offset,
                    batch.chunks,
                ],
                task_queue=TaskQueue.EMBEDDING,
                start_to_close_timeout=_EMBED_TIMEOUT,
                retry_policy=_RETRY_POLICY,
            )
            embedded += result.embedded_count
            if result.output_uri:
                embedding_uris.append(result.output_uri)
            offset += len(batch.chunks)
            batches_done += 1

        if offset < total_chunks:
            workflow.continue_as_new(
                IndexCorpusInput(
                    index_build_id=arg.index_build_id,
                    chunking_configuration_id=arg.chunking_configuration_id,
                    embedding_profile_id=embedding_profile_id,
                    document_ids=arg.document_ids,
                    chunks_materialized=True,
                    chunk_offset=offset,
                    total_chunks=total_chunks,
                    embedded=embedded,
                    embedding_uris=embedding_uris,
                )
            )

        await workflow.execute_activity(
            complete_index_build,
            args=[workflow_id, False],
            task_queue=TaskQueue.CHUNKING,
            start_to_close_timeout=_READ_TIMEOUT,
            retry_policy=_RETRY_POLICY,
        )
        return {
            "status": "ready",
            "index_build_id": arg.index_build_id,
            "total_chunks": total_chunks,
            "embedded": embedded,
            "embedding_uris": embedding_uris,
        }
