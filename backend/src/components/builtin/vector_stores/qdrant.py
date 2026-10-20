from __future__ import annotations

from typing import Any

KEY = "qdrant"
VERSION = "1"
DISPLAY_NAME = "Qdrant"

PARAMS_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Qdrant indexer parameters",
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
            "minimum": 4,
            "default": 100,
            "title": "EF construction",
            "description": "Number of neighbors considered while building the HNSW graph. A higher value improves index quality at the cost of more time. The default value is 100.",
        },
        "max_neighbors": {
            "type": "integer",
            "minimum": 0,
            "default": 16,
            "title": "Max neighbors",
            "description": "Number of edges per node in the HNSW graph. A higher value improves recall at the cost of more memory. The default value is 16.",
        },
    },
}
