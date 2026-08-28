from __future__ import annotations

from typing import Any

KEY = "recursive"
VERSION = "1"
DISPLAY_NAME = "Recursive character splitter"
STRATEGY = "recursive"

PARAMS_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Recursive character chunker parameters",
    "type": "object",
    "additionalProperties": False,
    "required": ["chunk_size", "overlap"],
    "properties": {
        "chunk_size": {
            "type": "integer",
            "minimum": 1,
            "default": 1000,
            "title": "Chunk size",
            "description": "Target chunk length in characters.",
        },
        "overlap": {
            "type": "integer",
            "minimum": 0,
            "default": 200,
            "title": "Overlap",
            "description": "Characters shared between consecutive chunks.",
        },
        "separators": {
            "type": "array",
            "items": {"type": "string"},
            "default": ["\n\n", "\n", ". ", " ", ""],
            "title": "Separators",
            "description": "Split points tried in order, from coarsest to finest.",
        },
        "strip_headers_footers": {
            "type": "boolean",
            "default": True,
            "title": "Strip headers and footers",
            "description": "Drop the repeated page furniture before splitting.",
        },
    },
}

# `scope` is read by `ProfileService._assert_document_scope`: declaring `document` is what
# makes a chunker usable in v1.
CAPABILITIES: dict[str, Any] = {
    "scope": "document",
    "modalities": ["text"],
}
