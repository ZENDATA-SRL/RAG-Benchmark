from __future__ import annotations

import threading
from typing import IO

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.client import Config
from botocore.exceptions import ClientError

from src.infrastructure.storage.base import ObjectStorage
from src.settings import Settings

# Chosen so a 200 MB upload costs ~8 MB of buffers instead of 200 MB of resident memory
# Also the S3 minimum for every part of a multipart upload but the last.
_MULTIPART_CHUNK_BYTES = 8 * 1024 * 1024


class S3ObjectStorage(ObjectStorage):
    """S3-compatible object storage, used against MinIO in local and S3 in cloud.

    Reads and writes go through `upload_fileobj` / the streaming body of `get_object`, so
    neither direction ever materialises the whole file in memory. The client is
    thread-safe for the calls used here, but boto3 sessions are not, so one client is
    created per instance and instances are meant to be reused per process.
    """

    def __init__(self, settings: Settings) -> None:
        self._bucket = settings.storage_bucket
        self._endpoint = settings.storage_endpoint.rstrip("/")
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.storage_endpoint,
            aws_access_key_id=settings.storage_access_key,
            aws_secret_access_key=settings.storage_secret_key,
            region_name=settings.storage_region,
            use_ssl=settings.storage_secure,
            # MinIO only speaks path-style addressing.
            config=Config(s3={"addressing_style": "path"}, signature_version="s3v4"),
        )

    @property
    def bucket(self) -> str:
        """Name of the bucket every key is resolved against."""
        return self._bucket

    def put_stream(self, key: str, stream: IO[bytes], content_type: str) -> str:
        """Upload a readable stream in multipart chunks.

        Args:
            key: Destination key, built by `document_key` or `parse_key`.
            stream: Readable binary stream; consumed from the current position.
            content_type: MIME type stored as object metadata.

        Returns:
            The URI of the stored object.
        """
        self._client.upload_fileobj(
            stream,
            self._bucket,
            key,
            ExtraArgs={"ContentType": content_type},
            Config=self._transfer_config(),
        )
        return self.build_uri(key)

    def put_bytes(self, key: str, data: bytes, content_type: str) -> str:
        """Upload an in-memory payload, e.g. a serialised parse output."""
        self._client.put_object(
            Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
        )
        return self.build_uri(key)

    def get_stream(self, key: str) -> IO[bytes]:
        """Open the object for reading.

        The returned body is a network stream: the caller owns it and should close it,
        ideally with a `with` block.
        """
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        return response["Body"]

    def get_bytes(self, key: str) -> bytes:
        """Read the whole object into memory; intended for parse outputs, not documents."""
        with self.get_stream(key) as body:
            return body.read()

    def exists(self, key: str) -> bool:
        """Return whether the key exists, translating a 404 into `False`."""
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in {
                "404",
                "NoSuchKey",
                "NotFound",
            }:
                return False
            raise
        return True

    def build_uri(self, key: str) -> str:
        """Return the `s3://bucket/key` URI persisted in the database.

        The scheme-and-bucket form is kept instead of an HTTP URL because the endpoint is
        deployment-specific: a row written in local must stay resolvable in cloud.
        """
        return f"s3://{self._bucket}/{key}"

    def ensure_bucket(self) -> None:
        """Create the bucket if missing; used by tests, `minio-init` does it in local."""
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError:
            self._client.create_bucket(Bucket=self._bucket)

    @staticmethod
    def _transfer_config() -> TransferConfig:
        return TransferConfig(
            multipart_threshold=_MULTIPART_CHUNK_BYTES,
            multipart_chunksize=_MULTIPART_CHUNK_BYTES,
            use_threads=False,
        )


_client_lock = threading.Lock()
_client: S3ObjectStorage | None = None


def get_object_storage(settings: Settings) -> S3ObjectStorage:
    """Return the process-wide storage client.

    Creating a boto3 client costs tens of milliseconds and loads the botocore service
    model, so it is built once and shared: doing it per request would dominate the
    latency of an upload.
    """
    global _client
    with _client_lock:
        if _client is None:
            _client = S3ObjectStorage(settings)
        return _client
