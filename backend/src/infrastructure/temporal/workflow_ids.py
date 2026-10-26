from __future__ import annotations

import uuid
from collections.abc import Iterable

from src.core.hashing import composition_hash

# Names the API needs to launch work without importing the worker package: dependencies
# flow `temporal -> backend`, so the side that *starts* a workflow and the side that
# *serves* it read the same constants from here. Kept in infrastructure rather than in a
# domain module because several modules start workflows and the worker serves them all.
MATERIALIZE_CHUNKS_WORKFLOW = "MaterializeChunksWorkflow"
INDEX_CORPUS_WORKFLOW = "IndexCorpusWorkflow"
RUN_EXPERIMENT_WORKFLOW = "RunExperimentWorkflow"
CHUNKING_TASK_QUEUE = "chunking"
EMBEDDING_TASK_QUEUE = "embedding"
EXPERIMENTS_TASK_QUEUE = "experiments"


def materialize_workflow_id(
    chunking_configuration_id: uuid.UUID, document_ids: Iterable[uuid.UUID]
) -> str:
    """Deterministic id of a `MaterializeChunksWorkflow` run.

    The id is a function of the configuration and the *set* of documents, so relaunching
    the same materialisation is rejected by Temporal itself for a duplicate workflow id:
    idempotency is a property of the id, not application logic.
    """
    return materialize_workflow_id_for_composition(
        chunking_configuration_id, composition_hash(document_ids)
    )


def materialize_workflow_id_for_composition(
    chunking_configuration_id: uuid.UUID | str, document_set_hash: str
) -> str:
    """Same id as `materialize_workflow_id`, from an already computed composition hash.

    A corpus snapshot stores exactly this hash, so an index build can derive the id of its
    materialisation without loading the document ids into the workflow.
    """
    return f"materialize-{chunking_configuration_id}-{document_set_hash}"


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


def run_experiment_workflow_id(run_id: uuid.UUID | str) -> str:
    """Deterministic id of a `RunExperimentWorkflow`.

    One id per run, reused when the run is relaunched after an interruption: Temporal
    refuses a second launch while the first is open, and accepts it once it has closed.
    """
    return f"run-experiment-{run_id}"


def run_variant_workflow_id(
    run_id: uuid.UUID | str, variant_id: uuid.UUID | str
) -> str:
    """Deterministic id of the `RunVariantWorkflow` child of one variant of a run."""
    return f"run-variant-{run_id}-{variant_id}"
