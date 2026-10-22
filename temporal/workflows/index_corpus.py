from __future__ import annotations

import dataclasses
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ChildWorkflowError

with workflow.unsafe.imports_passed_through():
    from src.infrastructure.temporal.workflow_ids import (
        materialize_workflow_id_for_composition,
    )

    from temporal.activities.embed import embed_batch
    from temporal.activities.indexing import (
        complete_index_build,
        count_index_chunks,
        open_index_build,
        resolve_index_build,
    )
    from temporal.activities.vector_store import (
        prepare_index_collection,
        upsert_embedding_batch,
    )
    from temporal.task_queues import TaskQueue
    from temporal.workflows.materialize_chunks import (
        MaterializeChunksWorkflow,
        MaterializeInput,
    )

_READ_TIMEOUT = timedelta(seconds=30)
_MATERIALIZE_TIMEOUT = timedelta(hours=2)
_EMBED_TIMEOUT = timedelta(minutes=15)
_UPSERT_TIMEOUT = timedelta(minutes=5)
_RETRY_POLICY = RetryPolicy(maximum_attempts=3)
_EMBED_BATCH_SIZE = 100
# continue_as_new before embedding history grows too large.
_CONTINUE_AFTER_BATCHES = 100


@dataclasses.dataclass
class IndexCorpusInput:
    """Arguments of an index build run, threaded through `continue_as_new`.

    Only ids and counters: nothing here grows with the corpus, so the payload stays well
    under the codec limit however many documents or batches the build has.
    """

    index_build_id: str
    embedding_profile_id: str | None = None
    chunks_materialized: bool = False
    chunk_offset: int = 0
    total_chunks: int | None = None
    embedded: int = 0
    upserted: int = 0


@workflow.defn
class IndexCorpusWorkflow:
    """Materialise chunks for a snapshot, embed them and write them to the vector store.

    Chunk materialisation runs as the existing child workflow, paged over the snapshot.
    Each batch is then embedded to object storage and upserted from there into the
    build's collection, so a failed upsert never recomputes embeddings and a retried
    batch overwrites itself.
    """

    @workflow.run
    async def run(self, arg: IndexCorpusInput | str) -> dict:
        if isinstance(arg, str):
            arg = IndexCorpusInput(index_build_id=arg)
        try:
            return await self._run(arg)
        except (ActivityError, ChildWorkflowError):
            # Retries are exhausted or the error is permanent: record it on the build so
            # it does not stay `running` forever, then fail the workflow as well.
            await workflow.execute_activity(
                complete_index_build,
                args=[workflow.info().workflow_id, True],
                task_queue=TaskQueue.CHUNKING,
                start_to_close_timeout=_READ_TIMEOUT,
                retry_policy=_RETRY_POLICY,
            )
            raise

    async def _run(self, arg: IndexCorpusInput) -> dict:
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
                    document_ids=[],
                    chunking_configuration_id=build.chunking_configuration_id,
                    corpus_snapshot_id=build.corpus_snapshot_id,
                    total=build.document_count,
                ),
                # Same id a materialisation of these documents launched by list gets, so
                # the two entry points never run the same work twice.
                id=materialize_workflow_id_for_composition(
                    build.chunking_configuration_id, build.composition_hash
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
            await workflow.execute_activity(
                prepare_index_collection,
                arg.index_build_id,
                task_queue=TaskQueue.EMBEDDING,
                start_to_close_timeout=_UPSERT_TIMEOUT,
                retry_policy=_RETRY_POLICY,
            )
            arg = IndexCorpusInput(
                index_build_id=arg.index_build_id,
                embedding_profile_id=build.embedding_profile_id,
                chunks_materialized=True,
                total_chunks=total_chunks,
            )

        total_chunks = arg.total_chunks or 0
        embedding_profile_id = arg.embedding_profile_id
        assert embedding_profile_id is not None

        offset = arg.chunk_offset
        embedded = arg.embedded
        upserted = arg.upserted
        batches_done = 0

        while offset < total_chunks and batches_done < _CONTINUE_AFTER_BATCHES:
            result = await workflow.execute_activity(
                embed_batch,
                args=[
                    arg.index_build_id,
                    embedding_profile_id,
                    offset,
                    _EMBED_BATCH_SIZE,
                ],
                task_queue=TaskQueue.EMBEDDING,
                start_to_close_timeout=_EMBED_TIMEOUT,
                retry_policy=_RETRY_POLICY,
            )
            if result.embedded_count == 0:
                break
            embedded += result.embedded_count
            upserted += await workflow.execute_activity(
                upsert_embedding_batch,
                args=[arg.index_build_id, offset],
                task_queue=TaskQueue.EMBEDDING,
                start_to_close_timeout=_UPSERT_TIMEOUT,
                retry_policy=_RETRY_POLICY,
            )
            offset += result.embedded_count
            batches_done += 1

        if offset < total_chunks:
            workflow.continue_as_new(
                IndexCorpusInput(
                    index_build_id=arg.index_build_id,
                    embedding_profile_id=embedding_profile_id,
                    chunks_materialized=True,
                    chunk_offset=offset,
                    total_chunks=total_chunks,
                    embedded=embedded,
                    upserted=upserted,
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
            "upserted": upserted,
        }
