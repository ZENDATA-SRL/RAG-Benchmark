from __future__ import annotations

from temporal.workflows.index_corpus import IndexCorpusInput, IndexCorpusWorkflow
from temporal.workflows.materialize_chunks import (
    MaterializeChunksWorkflow,
    MaterializeInput,
)
from temporal.workflows.process_document import ProcessDocumentWorkflow
from temporal.workflows.run_experiment import (
    RunExperimentInput,
    RunExperimentWorkflow,
    RunVariantInput,
    RunVariantWorkflow,
)
from temporal.workflows.transfer_dataset import (
    TransferDatasetInput,
    TransferDatasetWorkflow,
)

ALL_WORKFLOWS = [
    ProcessDocumentWorkflow,
    MaterializeChunksWorkflow,
    IndexCorpusWorkflow,
    RunExperimentWorkflow,
    RunVariantWorkflow,
    TransferDatasetWorkflow,
]

__all__ = [
    "ALL_WORKFLOWS",
    "IndexCorpusInput",
    "IndexCorpusWorkflow",
    "MaterializeChunksWorkflow",
    "MaterializeInput",
    "ProcessDocumentWorkflow",
    "RunExperimentInput",
    "RunExperimentWorkflow",
    "RunVariantInput",
    "RunVariantWorkflow",
    "TransferDatasetInput",
    "TransferDatasetWorkflow",
]
