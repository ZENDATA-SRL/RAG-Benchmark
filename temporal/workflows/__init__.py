from __future__ import annotations

from temporal.workflows.index_corpus import IndexCorpusInput, IndexCorpusWorkflow
from temporal.workflows.materialize_chunks import (
    MaterializeChunksWorkflow,
    MaterializeInput,
)
from temporal.workflows.process_document import ProcessDocumentWorkflow

ALL_WORKFLOWS = [
    ProcessDocumentWorkflow,
    MaterializeChunksWorkflow,
    IndexCorpusWorkflow,
]

__all__ = [
    "ALL_WORKFLOWS",
    "IndexCorpusInput",
    "IndexCorpusWorkflow",
    "MaterializeChunksWorkflow",
    "MaterializeInput",
    "ProcessDocumentWorkflow",
]
