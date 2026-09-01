from __future__ import annotations

from typing import Any

KEY = "markdown"
VERSION = "1"
DISPLAY_NAME = "Markdown text splitter"
STRATEGY = "markdown"

PARAMS_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Markdown chunker parameters",
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
        "strip_headers_footers": {
            "type": "boolean",
            "default": True,
            "title": "Strip headers and footers",
            "description": "Drop the repeated page furniture before splitting.",
        },
        "headers_to_split_on": {
            "type": "array",
            "items": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 2,
                "maxItems": 2,
            },
            "default": [["#", "Header 1"], ["##", "Header 2"], ["###", "Header 3"]],
            "title": "Headers to split on",
            "description": "Markdown heading markers and the metadata key each one writes.",
        },
        "strip_headers": {
            "type": "boolean",
            "default": False,
            "title": "Strip headers",
            "description": "Remove the heading line from the chunk text; it stays in metadata either way.",
        },
    },
}

# `scope` is read by `ProfileService._assert_document_scope`: declaring `document` is what
# makes a chunker usable in v1.
CAPABILITIES: dict[str, Any] = {
    "scope": "document",
    "modalities": ["text"],
}
