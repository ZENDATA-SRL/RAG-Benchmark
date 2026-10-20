from __future__ import annotations

from typing import Any

KEY = "bedrock"
VERSION = "1"
DISPLAY_NAME = "Bedrock"

PARAMS_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Bedrock embedder parameters",
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "model_name": {
            "type": "string",
            "default": "amazon.titan-embed-image-v1",
            "title": "Model name",
            "description": "The name of the Bedrock model to use for embedding.",
        },
        "region": {
            "type": "string",
            "default": "us-east-1",
            "title": "Region",
            "description": "The region to use for the Bedrock API.",
        },
        "aws_access_key_id": {
            "type": "string",
            "default": "",
            "title": "AWS access key ID",
            "description": "The AWS access key ID to use for the Bedrock API.",
        },
        "aws_secret_access_key": {
            "type": "string",
            "default": "",
            "title": "AWS secret access key",
            "description": "The AWS secret access key to use for the Bedrock API.",
        },
    },
}
