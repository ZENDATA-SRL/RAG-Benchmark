from __future__ import annotations

from typing import Any

KEY = "rag_simple"
VERSION = "1"
DISPLAY_NAME = "Simple RAG chain"

PROVIDERS = ("openai", "bedrock")

# Everything that changes the answers is a parameter, so it enters the profile hash. The
# credentials are not: they are read from the worker's environment and never stored.
PARAMS_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Simple RAG chain parameters",
    "type": "object",
    "additionalProperties": False,
    "required": ["provider", "model", "system_prompt"],
    "properties": {
        "provider": {
            "type": "string",
            "enum": list(PROVIDERS),
            "title": "Provider",
            "description": "Who serves the chat model.",
        },
        "model": {
            "type": "string",
            "minLength": 1,
            "title": "Model",
            "description": "Chat model id, e.g. gpt-4o-mini or a Bedrock model id.",
        },
        "system_prompt": {
            "type": "string",
            "minLength": 1,
            "title": "System prompt",
            "description": (
                "Instructions given before the numbered passages and the question."
            ),
        },
        "temperature": {
            "type": "number",
            "minimum": 0,
            "maximum": 2,
            "default": 0,
            "title": "Temperature",
        },
        "max_tokens": {
            "type": "integer",
            "minimum": 1,
            "default": 1024,
            "title": "Max output tokens",
        },
        "region": {
            "type": "string",
            "title": "Region",
            "description": "Bedrock only; without it the AWS profile's region applies.",
        },
    },
}

# One search, every hit in the prompt and an answer that cites the passages it used.
CAPABILITIES: dict[str, Any] = {"supports_citations": True}
