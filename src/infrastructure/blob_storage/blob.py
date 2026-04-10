from __future__ import annotations

import logging
import os
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from urllib.parse import unquote, urlparse

from azure.core.exceptions import ResourceExistsError
from azure.storage.blob import BlobServiceClient, PublicAccess
from azure.storage.blob.aio import BlobClient as AioBlobClient

logger = logging.getLogger(__name__)

_AZ_CONTAINER_INVALID = re.compile(r"[^a-z0-9-]")
_MULTI_HYPHEN = re.compile(r"-{2,}")
_CTRL_OR_UNSAFE_SEGMENT = re.compile(r'[\x00-\x1f\x7f<>:"|?*#\\]')
_SPACE_RUN = re.compile(r"\s+")


def normalize_storage_segment(value: str, *, default: str = "unnamed") -> str:
    """
    NFC unicode, basename-only, strip unsafe/control characters and path noise,
    collapse whitespace to hyphens — stable names for blobs and DB document keys.
    """
    s = unicodedata.normalize("NFC", (value or "").strip())
    s = Path(s).name
    if not s or s in (".", ".."):
        return default
    s = _CTRL_OR_UNSAFE_SEGMENT.sub("-", s)
    s = _SPACE_RUN.sub("-", s)
    s = _MULTI_HYPHEN.sub("-", s).strip("-")
    s = s.strip(". ")
    if not s:
        return default
    return s


def azure_safe_container_name(name: str, *, fallback: str = "datasets") -> str:
    """
    Azure container names: 3–63 chars, lowercase letters, digits, hyphens only;
    must start/end with alphanumeric; no consecutive hyphens.
    """
    s = name.lower()
    s = _AZ_CONTAINER_INVALID.sub("-", s)
    s = _MULTI_HYPHEN.sub("-", s).strip("-")
    if not s:
        s = fallback.lower()
        s = _AZ_CONTAINER_INVALID.sub("-", s)
        s = _MULTI_HYPHEN.sub("-", s).strip("-")
    if len(s) < 3:
        s = (s + "x" * 3)[:3]
    if len(s) > 63:
        s = s[:63].rstrip("-")
        if len(s) < 3:
            s = (s + "x" * 3)[:3]
    return s


@lru_cache(maxsize=1)
def _service_client() -> BlobServiceClient:
    conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    return BlobServiceClient.from_connection_string(conn_str)


def insert_blob(container_name: str, blob_name: str, blob_content: bytes) -> str:
    """
    Uploads bytes to Azure Blob Storage and returns the blob URL.

    Requires `AZURE_STORAGE_CONNECTION_STRING`.
    """
    logger.debug(
        "blob.insert.start",
        extra={
            "event": "blob.insert.start",
            "container": container_name,
            "blob_name": blob_name,
            "size_bytes": len(blob_content),
        },
    )
    service = _service_client()
    container = service.get_container_client(container_name)
    try:
        container.create_container(public_access=PublicAccess.BLOB)
    except ResourceExistsError:
        pass

    blob = container.get_blob_client(blob_name)
    blob.upload_blob(blob_content, overwrite=True)
    url = blob.url
    logger.debug(
        "blob.insert.done",
        extra={
            "event": "blob.insert.done",
            "container": container_name,
            "blob_name": blob_name,
            "size_bytes": len(blob_content),
        },
    )
    return url


def _parse_container_and_blob_from_url(blob_url: str) -> tuple[str, str]:
    """
    Azure blob URLs are typically: https://{account}.blob.core.windows.net/{container}/{blob}
    """
    parsed = urlparse(blob_url)
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        raise ValueError(
            f"Invalid blob URL (missing container/blob path): {blob_url!r}"
        )
    container = unquote(parts[0])
    blob_name = unquote("/".join(parts[1:]))
    return container, blob_name


async def get_blob_from_url(blob_url: str) -> bytes:
    """
    Downloads blob bytes from a URL.

    - If `AZURE_STORAGE_CONNECTION_STRING` is set, downloads using account auth.
    - Otherwise, attempts an anonymous/SAS URL download.
    """
    # conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")

    # if conn_str:
    #     container_name, blob_name = _parse_container_and_blob_from_url(blob_url)
    #     logger.debug(
    #         "blob.download.start",
    #         extra={
    #             "event": "blob.download.start",
    #             "container": container_name,
    #             "blob_name": blob_name,
    #             "auth": "connection_string",
    #         },
    #     )
    #     async with AioBlobServiceClient.from_connection_string(
    #         conn_str
    #     ) as service_client:
    #         blob_client = service_client.get_blob_client(container_name, blob_name)
    #         stream = await blob_client.download_blob()
    #         data = await stream.readall()
    #     logger.debug(
    #         "blob.download.done",
    #         extra={
    #             "event": "blob.download.done",
    #             "container": container_name,
    #             "blob_name": blob_name,
    #             "size_bytes": len(data),
    #             "auth": "connection_string",
    #         },
    #     )
    #     return data

    # logger.debug(
    #     "blob.download.start",
    #     extra={
    #         "event": "blob.download.start",
    #         "auth": "blob_url",
    #         "url_host": urlparse(blob_url).netloc or "unknown",
    #     },
    # )
    async with AioBlobClient.from_blob_url(blob_url) as blob_client:
        stream = await blob_client.download_blob()
        data = await stream.readall()
    logger.debug(
        "blob.download.done",
        extra={
            "event": "blob.download.done",
            "auth": "blob_url",
            "url_host": urlparse(blob_url).netloc or "unknown",
            "size_bytes": len(data),
        },
    )
    return data
