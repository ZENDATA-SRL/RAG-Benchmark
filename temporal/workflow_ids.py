from __future__ import annotations

from src.infrastructure.temporal.workflow_ids import (
    index_corpus_workflow_id,
    materialize_workflow_id,
    process_document_workflow_id,
)

# The convention lives in the backend because the API is what *starts* the workflows and
# must compute the same id the worker serves; re-exported here so worker code keeps
# importing it from its own package.
__all__ = [
    "index_corpus_workflow_id",
    "materialize_workflow_id",
    "process_document_workflow_id",
]
