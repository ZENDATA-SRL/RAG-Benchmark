from __future__ import annotations

from src.infrastructure.storage.base import (
    DOCUMENTS_PREFIX,
    PARSES_PREFIX,
    ObjectStorage,
    document_key,
    parse_key,
)
from src.infrastructure.storage.s3 import S3ObjectStorage, get_object_storage

__all__ = [
    "DOCUMENTS_PREFIX",
    "PARSES_PREFIX",
    "ObjectStorage",
    "S3ObjectStorage",
    "document_key",
    "get_object_storage",
    "parse_key",
]
