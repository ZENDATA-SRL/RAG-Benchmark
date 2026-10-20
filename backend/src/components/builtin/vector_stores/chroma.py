from __future__ import annotations

from typing import Any

KEY = "chromadb"
VERSION = "1"
DISPLAY_NAME = "ChromaDB"

PARAMS_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "ChromaDB indexer parameters",
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "space": {
            "type": "string",
            "enum": ["cosine", "l2", "ip"],
            "enumNames": ["Cosine", "L2 (Euclidean)", "Inner product"],
            "default": "cosine",
            "title": "Space",
            "description": "The distance metric to use for the embedding space.",
        },
        "ef_construction": {
            "type": "integer",
            "default": 100,
            "title": "EF construction",
            "description": "Determines the size of the candidate list used to select neighbors during index creation. A higher value improves index quality at the cost of more memory and time, while a lower value speeds up construction with reduced accuracy. The default value is 100.",
        },
        "ef_search": {
            "type": "integer",
            "default": 100,
            "title": "EF search",
            "description": "Determines the size of the dynamic candidate list used while searching for the nearest neighbors. A higher value improves recall and accuracy by exploring more potential neighbors but increases query time and computational cost, while a lower value results in faster but less accurate searches. The default value is 100. This field can be modified after creation.",
        },
        "max_neighbors": {
            "type": "integer",
            "minimum": 1,
            "default": 16,
            "title": "Max neighbors",
            "description": "The maximum number of neighbors (connections) that each node in the graph can have during the construction of the index. A higher value results in a denser graph, leading to better recall and accuracy during searches but increases memory usage and construction time. A lower value creates a sparser graph, reducing memory usage and construction time but at the cost of lower search accuracy and recall. The default value is 16.",
        },
        "num_threads": {
            "type": "integer",
            "minimum": 1,
            "title": "Num threads",
            "description": "The number of threads to use during index construction or search operations. The default value is the number of available CPU cores (multiprocessing.cpu_count()). This field can be modified after creation.",
        },
        "batch_size": {
            "type": "integer",
            "minimum": 2,
            "default": 100,
            "title": "Batch size",
            "description": "The number of vectors to process in each batch during index operations. The default value is 100. This field can be modified after creation.",
        },
        "sync_threshold": {
            "type": "integer",
            "minimum": 2,
            "default": 1000,
            "title": "Sync threshold",
            "description": "Determines when to synchronize the index with persistent storage. The default value is 1000. This field can be modified after creation.",
        },
        "resize_factor": {
            "type": "number",
            "minimum": 1,
            "default": 1.2,
            "title": "Resize factor",
            "description": "Controls how much the index grows when it needs to be resized. The default value is 1.2. This field can be modified after creation.",
        },
    },
}
