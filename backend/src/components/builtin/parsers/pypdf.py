from __future__ import annotations

from typing import Any

KEY = "pypdf"
VERSION = "1"
DISPLAY_NAME = "PyPDF"

PARAMS_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "PyPDF parser parameters",
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "extract_images": {
            "type": "boolean",
            "default": False,
            "title": "Extract images",
            "description": "Reserved for the multimodal path; ignored while only text is indexed.",
        }
    },
}

CAPABILITIES: dict[str, Any] = {
    "formats": ["pdf"],
    "modalities": ["text"],
}
