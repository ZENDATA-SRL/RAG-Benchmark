from __future__ import annotations

from temporal.activities.chunking import ChunkResultOutput, chunk_document
from temporal.activities.embed import EmbedBatchOutput, embed_batch
from temporal.activities.indexing import (
    ChunkBatch,
    ChunkForEmbedding,
    IndexBuildResolved,
    complete_index_build,
    count_index_chunks,
    fetch_index_chunk_batch,
    open_index_build,
    resolve_index_build,
)
from temporal.activities.materialization import (
    documents_needing_chunking,
    open_materialization_run,
    record_progress,
    summarize_run,
)
from temporal.activities.parsing import ParseResult, parse_document
from temporal.activities.reads import ConfigurationResolved, resolve_configuration

# Every activity the worker registers, in one place so `worker.py` and the workflow tests
# import the same set.
ALL_ACTIVITIES = [
    resolve_configuration,
    parse_document,
    chunk_document,
    open_materialization_run,
    documents_needing_chunking,
    record_progress,
    summarize_run,
    resolve_index_build,
    open_index_build,
    complete_index_build,
    count_index_chunks,
    fetch_index_chunk_batch,
    embed_batch,
]

__all__ = [
    "ALL_ACTIVITIES",
    "ChunkBatch",
    "ChunkForEmbedding",
    "ChunkResultOutput",
    "ConfigurationResolved",
    "EmbedBatchOutput",
    "IndexBuildResolved",
    "ParseResult",
    "chunk_document",
    "complete_index_build",
    "count_index_chunks",
    "documents_needing_chunking",
    "embed_batch",
    "fetch_index_chunk_batch",
    "open_index_build",
    "open_materialization_run",
    "parse_document",
    "record_progress",
    "resolve_configuration",
    "resolve_index_build",
    "summarize_run",
]
