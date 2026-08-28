from __future__ import annotations

import hashlib
import io
import os
import uuid

import pytest
from src.infrastructure.storage import document_key, parse_key
from src.infrastructure.storage.s3 import S3ObjectStorage
from src.settings import Settings

pytestmark = pytest.mark.integration

# Larger than the 8 MB multipart threshold, so the test actually exercises the chunked
# upload path and not the single-shot one.
PAYLOAD_BYTES = 10 * 1024 * 1024


@pytest.fixture
def storage(settings: Settings) -> S3ObjectStorage:
    """Storage client pointed at a dedicated bucket, skipping if MinIO is unreachable."""
    test_settings = settings.model_copy(update={"storage_bucket": f"{settings.storage_bucket}-test"})
    client = S3ObjectStorage(test_settings)
    try:
        client.ensure_bucket()
    except Exception as error:  # pragma: no cover - environment problem
        pytest.skip(f"object storage not reachable: {error}")
    return client


def test_put_and_get_stream_roundtrip_preserves_sha256(storage: S3ObjectStorage) -> None:
    """10 MB written in streaming and read back must hash identically."""
    payload = os.urandom(PAYLOAD_BYTES)
    expected = hashlib.sha256(payload).hexdigest()
    key = f"tests/{uuid.uuid4().hex}.bin"

    uri = storage.put_stream(key, io.BytesIO(payload), "application/octet-stream")
    assert uri == f"s3://{storage.bucket}/{key}"

    digest = hashlib.sha256()
    with storage.get_stream(key) as body:
        while chunk := body.read(1024 * 1024):
            digest.update(chunk)

    assert digest.hexdigest() == expected


def test_exists_reflects_presence(storage: S3ObjectStorage) -> None:
    key = f"tests/{uuid.uuid4().hex}.bin"
    assert storage.exists(key) is False

    storage.put_bytes(key, b"present", "application/octet-stream")
    assert storage.exists(key) is True


def test_put_bytes_and_get_bytes_roundtrip(storage: S3ObjectStorage) -> None:
    key = f"tests/{uuid.uuid4().hex}.json"
    payload = b'{"pages": []}'

    storage.put_bytes(key, payload, "application/json")

    assert storage.get_bytes(key) == payload


def test_same_content_hash_writes_the_same_key() -> None:
    """The key derives from the content, so a re-upload overwrites instead of duplicating."""
    content_hash = hashlib.sha256(b"content").hexdigest()
    assert document_key(content_hash, "a.pdf") == document_key(content_hash, "b.pdf")


def test_document_key_layout() -> None:
    content_hash = hashlib.sha256(b"content").hexdigest()
    assert document_key(content_hash, "Report.PDF") == (
        f"documents/{content_hash[:2]}/{content_hash}.pdf"
    )


def test_parse_key_groups_by_profile() -> None:
    """Two profiles parsing the same document must not overwrite each other (RT-O02)."""
    content_hash = hashlib.sha256(b"content").hexdigest()
    assert parse_key("aaaa", content_hash) != parse_key("bbbb", content_hash)
