from __future__ import annotations

from temporal.activities.chunking import ChunkResultOutput, chunk_document
from temporal.activities.embed import EmbedBatchOutput, embed_batch
from temporal.activities.experiments import (
    ExperimentRunResolved,
    fail_experiment_run,
    finish_experiment_run,
    list_unfinished_executions,
    mark_execution_failed,
    open_experiment_run,
    record_run_progress,
    retrieve_question,
)
from temporal.activities.indexing import (
    IndexBuildResolved,
    complete_index_build,
    count_index_chunks,
    open_index_build,
    resolve_index_build,
)
from temporal.activities.materialization import (
    SnapshotDocumentsPage,
    documents_needing_chunking,
    open_materialization_run,
    record_progress,
    snapshot_documents_needing_chunking,
    summarize_run,
)
from temporal.activities.parsing import ParseResult, parse_document
from temporal.activities.reads import ConfigurationResolved, resolve_configuration
from temporal.activities.vector_store import (
    prepare_index_collection,
    upsert_embedding_batch,
)

# Every activity the worker registers, in one place so `worker.py` and the workflow tests
# import the same set.
ALL_ACTIVITIES = [
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
    embed_batch,
    prepare_index_collection,
    upsert_embedding_batch,
    open_experiment_run,
    list_unfinished_executions,
    retrieve_question,
    mark_execution_failed,
    record_run_progress,
    finish_experiment_run,
    fail_experiment_run,
]

__all__ = [
    "ALL_ACTIVITIES",
    "ChunkResultOutput",
    "ConfigurationResolved",
    "EmbedBatchOutput",
    "ExperimentRunResolved",
    "IndexBuildResolved",
    "ParseResult",
    "SnapshotDocumentsPage",
    "chunk_document",
    "complete_index_build",
    "count_index_chunks",
    "documents_needing_chunking",
    "embed_batch",
    "fail_experiment_run",
    "finish_experiment_run",
    "list_unfinished_executions",
    "mark_execution_failed",
    "open_experiment_run",
    "open_index_build",
    "open_materialization_run",
    "parse_document",
    "prepare_index_collection",
    "record_progress",
    "record_run_progress",
    "resolve_configuration",
    "resolve_index_build",
    "retrieve_question",
    "snapshot_documents_needing_chunking",
    "summarize_run",
    "upsert_embedding_batch",
]
