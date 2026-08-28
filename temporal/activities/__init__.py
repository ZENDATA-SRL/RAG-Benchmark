from __future__ import annotations

from temporal.activities.chunking import ChunkResultOutput, chunk_document
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
]

__all__ = [
    "ALL_ACTIVITIES",
    "ChunkResultOutput",
    "ConfigurationResolved",
    "ParseResult",
    "chunk_document",
    "documents_needing_chunking",
    "open_materialization_run",
    "parse_document",
    "record_progress",
    "resolve_configuration",
    "summarize_run",
]
