from __future__ import annotations

import uuid
from collections.abc import Iterable

from src.core.hashing import composition_hash

# Names the API needs to launch work without importing the worker package: dependencies
# flow `temporal -> backend`, so the side that *starts* a workflow and the side that
# *serves* it read the same constants from here.
MATERIALIZE_CHUNKS_WORKFLOW = "MaterializeChunksWorkflow"
INDEX_CORPUS_WORKFLOW = "IndexCorpusWorkflow"
CHUNKING_TASK_QUEUE = "chunking"
EMBEDDING_TASK_QUEUE = "embedding"


def materialize_workflow_id(
    chunking_configuration_id: uuid.UUID, document_ids: Iterable[uuid.UUID]
) -> str:
    """Deterministic id of a `MaterializeChunksWorkflow` run.

    The id is a function of the configuration and the *set* of documents, so relaunching
    the same materialisation is rejected by Temporal itself for a duplicate workflow id:
    idempotency is a property of the id, not application logic (RT-O01).
    """
    return f"materialize-{chunking_configuration_id}-{composition_hash(document_ids)}"


def index_corpus_workflow_id(index_build_id: uuid.UUID | str) -> str:
    """Deterministic id of an `IndexCorpusWorkflow` run."""
    return f"index-corpus-{index_build_id}"


def process_document_workflow_id(
    document_id: uuid.UUID | str, chunking_configuration_id: uuid.UUID | str
) -> str:
    """Deterministic id of a `ProcessDocumentWorkflow` child.

    One durable execution per (document, configuration): a child that already ran for the
    pair is reused instead of started again, which is what lets a re-run find everything in
    cache and complete without work.
    """
    return f"process-doc-{document_id}-{chunking_configuration_id}"
