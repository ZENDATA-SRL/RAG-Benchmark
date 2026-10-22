from __future__ import annotations

from pathlib import PurePosixPath
from typing import IO, Protocol, runtime_checkable

DOCUMENTS_PREFIX = "documents"
PARSES_PREFIX = "parses"


@runtime_checkable
class ObjectStorage(Protocol):
    """Blob storage seen by the application: keys in, streams out.

    Deliberately narrow so that the S3 implementation can be swapped for another
    backend without touching callers. Every method works on a *key*; turning a key into
    something persistable in the database is `build_uri`'s job.
    """

    def put_stream(self, key: str, stream: IO[bytes], content_type: str) -> str:
        """Store the content of a readable stream and return its URI."""
        ...

    def put_bytes(self, key: str, data: bytes, content_type: str) -> str:
        """Store an in-memory payload and return its URI."""
        ...

    def get_stream(self, key: str) -> IO[bytes]:
        """Open the object for reading without buffering it whole."""
        ...

    def get_bytes(self, key: str) -> bytes:
        """Read the object entirely into memory; only for small payloads."""
        ...

    def exists(self, key: str) -> bool:
        """Return whether the key is already present."""
        ...

    def build_uri(self, key: str) -> str:
        """Return the stable URI stored in `documents.storage_uri` and friends."""
        ...


def document_key(content_hash: str, filename: str) -> str:
    """Build the storage key of an original document.

    Shape: `documents/{content_hash}/{stem}{ext}`. The digest is the prefix, so uploading
    the same file twice writes the same object and deduplication costs nothing, while the
    original file name stays readable in the key.

    Args:
        content_hash: Hex sha-256 of the file content.
        filename: Original file name, kept in the key with a lowercased extension.

    Returns:
        Storage key, without bucket and without scheme.
    """
    path = PurePosixPath(filename)
    suffix = path.suffix.lower()
    return f"{DOCUMENTS_PREFIX}/{content_hash}/{path.stem}{suffix}"


def parse_key(parsing_profile_config_hash: str, content_hash: str) -> str:
    """Build the storage key of a parsing output.

    Shape: `parses/{parsing_profile_config_hash}/{content_hash}.json`. Grouping by
    profile hash first means the whole output of one parsing configuration is a single
    prefix, so re-parsing with different parameters never overwrites a previous result
    and both stay inspectable.

    Args:
        parsing_profile_config_hash: `parsing_profiles.config_hash`.
        content_hash: `documents.content_hash` of the parsed document.

    Returns:
        Storage key, without bucket and without scheme.
    """
    return f"{PARSES_PREFIX}/{parsing_profile_config_hash}/{content_hash}.json"


def storage_key(storage_uri: str) -> str:
    """Turn a stored `s3://bucket/key` URI back into the key the storage client expects.

    The inverse of `build_uri`: rows persist the URI because the endpoint is
    deployment-specific, so every reader of a stored artefact needs this one step back.

    Args:
        storage_uri: Value of a column such as `documents.storage_uri`.

    Returns:
        Storage key, without bucket and without scheme.
    """
    without_scheme = storage_uri.removeprefix("s3://")
    _, _, key = without_scheme.partition("/")
    return key
