from __future__ import annotations

from temporal.workflows.materialize_chunks import (
    MaterializeChunksWorkflow,
    MaterializeInput,
)
from temporal.workflows.process_document import ProcessDocumentWorkflow

ALL_WORKFLOWS = [ProcessDocumentWorkflow, MaterializeChunksWorkflow]

__all__ = [
    "ALL_WORKFLOWS",
    "MaterializeChunksWorkflow",
    "MaterializeInput",
    "ProcessDocumentWorkflow",
]
