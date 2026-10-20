from __future__ import annotations

from typing import Any

KEY = "openai"
VERSION = "1"
DISPLAY_NAME = "OpenAI"

PARAMS_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "OpenAI embedder parameters",
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "model_name": {
            "type": "string",
            "default": "text-embedding-3-small",
            "title": "Model name",
            "description": "The name of the OpenAI model to use for embedding.",
        },
        "api_key": {
            "type": "string",
            "default": "",
            "title": "API key",
            "description": "The API key to use for the OpenAI API.",
        },
    },
}
