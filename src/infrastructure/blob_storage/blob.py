from __future__ import annotations

import logging
import os
from functools import lru_cache
from urllib.parse import unquote, urlparse

from azure.core.exceptions import ResourceExistsError
from azure.storage.blob import BlobServiceClient
from azure.storage.blob.aio import BlobClient as AioBlobClient
from azure.storage.blob.aio import BlobServiceClient as AioBlobServiceClient

logger = logging.getLogger(__name__)


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
        container.create_container()
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
    conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    if conn_str:
        container_name, blob_name = _parse_container_and_blob_from_url(blob_url)
        logger.debug(
            "blob.download.start",
            extra={
                "event": "blob.download.start",
                "container": container_name,
                "blob_name": blob_name,
                "auth": "connection_string",
            },
        )
        async with AioBlobServiceClient.from_connection_string(
            conn_str
        ) as service_client:
            blob_client = service_client.get_blob_client(container_name, blob_name)
            stream = await blob_client.download_blob()
            data = await stream.readall()
        logger.debug(
            "blob.download.done",
            extra={
                "event": "blob.download.done",
                "container": container_name,
                "blob_name": blob_name,
                "size_bytes": len(data),
                "auth": "connection_string",
            },
        )
        return data

    logger.debug(
        "blob.download.start",
        extra={
            "event": "blob.download.start",
            "auth": "blob_url",
            "url_host": urlparse(blob_url).netloc or "unknown",
        },
    )
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
