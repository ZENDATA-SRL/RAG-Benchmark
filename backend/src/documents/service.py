from __future__ import annotations

import hashlib
import logging
import tempfile
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import IO

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from src.core.get_or_create import get_or_create
from src.documents.exceptions import (
    DocumentContentUnavailableError,
    DocumentNotFoundError,
    EmptyFileError,
    FileTooLargeError,
    UnsupportedMimeTypeError,
)
from src.documents.models import Document
from src.documents.repository import DocumentRepository
from src.infrastructure.database.enums import DocumentStatus, FileOutcome
from src.infrastructure.storage import ObjectStorage, document_key
from src.settings import Settings
from src.sources.models import DocumentProvenance
from src.sources.repository import DocumentProvenanceRepository

logger = logging.getLogger(__name__)

# Read size of the spool loop: large enough that hashing a 200 MB file is not syscall-bound,
# small enough to stay irrelevant to the memory profile.
_READ_CHUNK_BYTES = 1024 * 1024

# Above this the spool rolls over from memory to a temporary file on disk, so a big upload
# costs disk and not resident memory (RF-S12).
_SPOOL_MAX_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class UploadCandidate:
    """One file of an upload request, as the service sees it."""

    filename: str
    content_type: str
    stream: IO[bytes]


@dataclass(frozen=True)
class UploadOutcome:
    """What happened to one file of an upload request."""

    filename: str
    outcome: FileOutcome
    document_id: uuid.UUID | None = None
    error_reason: str | None = None


class DocumentService:
    """Acquisition of documents: content hashing, storage, deduplication, provenance.

    The identity of a document is its content, never its name or its origin. Uploading the
    same bytes twice therefore yields one row with two provenances (RF-S06), which is what
    makes the same file arriving from two sources one document in every later metric.

    A file is read exactly once. The storage key derives from the sha-256, which is only
    known after the last byte, so the stream is spooled while it is hashed instead of being
    read twice or buffered whole (RF-S12). The spool was preferred over a staging key plus a
    server-side copy: it needs no cleanup path and no second round trip, and the cost is
    local disk that is already required to receive a multipart body.
    """

    def __init__(
        self, session: AsyncSession, storage: ObjectStorage, settings: Settings
    ) -> None:
        self.session = session
        self.storage = storage
        self.settings = settings
        self.documents = DocumentRepository(session)
        self.provenances = DocumentProvenanceRepository(session)

    async def ingest_upload(
        self,
        stream: IO[bytes],
        *,
        filename: str,
        content_type: str,
        connection_id: uuid.UUID,
        original_uri: str | None = None,
    ) -> tuple[Document, bool]:
        """Bring one uploaded file into the platform.

        Args:
            stream: Readable binary stream of the file, consumed once.
            filename: Name declared by the client, kept for display and for the extension.
            content_type: MIME type declared by the client.
            connection_id: Connection the file is attributed to, for provenance (RF-S05).
            original_uri: How the file was identified at the source; defaults to `filename`,
                which is all the identity a manual upload has.

        Returns:
            The document and whether it already existed.

        Raises:
            UnsupportedMimeTypeError: If the MIME type is not accepted.
            FileTooLargeError: If the file exceeds `max_upload_bytes`.
            EmptyFileError: If the file has no content.
        """
        self._assert_supported(content_type)

        spool, content_hash, size_bytes = await run_in_threadpool(
            self._spool_and_hash, stream, self.settings.max_upload_bytes
        )
        try:
            if size_bytes == 0:
                raise EmptyFileError(filename)

            document, was_duplicate = await self._get_or_create_document(
                content_hash=content_hash,
                filename=filename,
                content_type=content_type,
                size_bytes=size_bytes,
            )

            if not was_duplicate:
                await self._store_content(document, spool, content_type)

            await self._record_provenance(
                document.id, connection_id, original_uri or filename
            )
            return document, was_duplicate
        finally:
            spool.close()

    async def ingest_upload_batch(
        self,
        candidates: Sequence[UploadCandidate],
        *,
        connection_id: uuid.UUID,
    ) -> list[UploadOutcome]:
        """Ingest several files, isolating the failure of each from the others.

        One rejected or broken file must not discard the ones that were fine (RF-S11), so
        each file is processed in its own savepoint and its outcome reported individually.
        The request therefore succeeds even when some files did not.

        Args:
            candidates: Files to ingest, in the order the client sent them.
            connection_id: Connection every file is attributed to.

        Returns:
            One outcome per file, in the same order.
        """
        outcomes: list[UploadOutcome] = []
        for candidate in candidates:
            outcomes.append(await self._ingest_one(candidate, connection_id))
        return outcomes

    async def get(self, document_id: uuid.UUID) -> Document:
        """Return a document by id.

        Raises:
            DocumentNotFoundError: If it does not exist.
        """
        document = await self.documents.get_by_id(document_id)
        if document is None:
            raise DocumentNotFoundError(document_id)
        return document

    async def list(
        self, *, status: DocumentStatus | None = None, limit: int = 50, offset: int = 0
    ) -> tuple[Sequence[Document], int]:
        """List documents with their total count, optionally filtered by status."""
        items = await self.documents.list(status=status, limit=limit, offset=offset)
        total = await self.documents.count(status=status)
        return items, total

    async def list_provenances(
        self, document_id: uuid.UUID
    ) -> Sequence[DocumentProvenance]:
        """List where a document came from, so the UI can link back to the original (RT-U06).

        Raises:
            DocumentNotFoundError: If the document does not exist.
        """
        await self.get(document_id)
        return await self.provenances.list_by_document(document_id)

    async def set_metadata(
        self, document_id: uuid.UUID, metadata: dict[str, object]
    ) -> Document:
        """Replace the metadata of a document (RF-C02).

        Metadata lives on the document and not on the corpus membership because it
        describes the file, and the same file in two corpora must not be described twice.

        Raises:
            DocumentNotFoundError: If the document does not exist.
        """
        document = await self.get(document_id)
        document.document_metadata = dict(metadata)
        await self.session.flush()
        return document

    async def open_content(self, document_id: uuid.UUID) -> tuple[Document, IO[bytes]]:
        """Open the stored bytes of a document for streaming back to the client.

        Returns:
            The document and an open stream the caller must close.

        Raises:
            DocumentNotFoundError: If the document does not exist.
            DocumentContentUnavailableError: If the content was never stored, i.e. the
                acquisition is still running or failed.
        """
        document = await self.get(document_id)
        if document.status is not DocumentStatus.STORED:
            raise DocumentContentUnavailableError(document_id, document.status)

        key = document_key(document.content_hash, document.filename)
        stream = await run_in_threadpool(self.storage.get_stream, key)
        return document, stream

    async def _ingest_one(
        self, candidate: UploadCandidate, connection_id: uuid.UUID
    ) -> UploadOutcome:
        """Ingest one file of a batch, translating any failure into an outcome."""
        try:
            async with self.session.begin_nested():
                document, was_duplicate = await self.ingest_upload(
                    candidate.stream,
                    filename=candidate.filename,
                    content_type=candidate.content_type,
                    connection_id=connection_id,
                )
        except UnsupportedMimeTypeError as error:
            return UploadOutcome(
                filename=candidate.filename,
                outcome=FileOutcome.SKIPPED_UNSUPPORTED,
                error_reason=error.message,
            )
        except (FileTooLargeError, EmptyFileError, SQLAlchemyError) as error:
            logger.warning("upload rejected for %s: %s", candidate.filename, error)
            return UploadOutcome(
                filename=candidate.filename,
                outcome=FileOutcome.FAILED,
                error_reason=str(error),
            )

        if document.status is DocumentStatus.FAILED:
            return UploadOutcome(
                filename=candidate.filename,
                outcome=FileOutcome.FAILED,
                document_id=document.id,
                error_reason=document.error,
            )

        outcome = (
            FileOutcome.SKIPPED_DUPLICATE if was_duplicate else FileOutcome.IMPORTED
        )
        return UploadOutcome(
            filename=candidate.filename, outcome=outcome, document_id=document.id
        )

    def _assert_supported(self, content_type: str) -> None:
        """Reject a MIME type this deployment cannot parse."""
        allowed = self.settings.allowed_mime_types
        if content_type not in allowed:
            raise UnsupportedMimeTypeError(content_type, allowed)

    async def _get_or_create_document(
        self,
        *,
        content_hash: str,
        filename: str,
        content_type: str,
        size_bytes: int,
    ) -> tuple[Document, bool]:
        """Resolve the document for a content hash, creating it as `fetching` if new.

        Returns:
            The document and whether it already existed, which is what tells the caller
            not to rewrite storage and to report `skipped_duplicate`.
        """
        existing = await self.documents.get_by_content_hash(content_hash)
        if existing is not None:
            return existing, True

        created: list[Document] = []

        async def create() -> Document:
            document = self.documents.add(
                Document(
                    content_hash=content_hash,
                    filename=filename,
                    mime_type=content_type,
                    size_bytes=size_bytes,
                    # Known before the upload because the key derives from the content,
                    # so the row is complete even while the bytes are still in flight.
                    storage_uri=self.storage.build_uri(
                        document_key(content_hash, filename)
                    ),
                    status=DocumentStatus.FETCHING,
                )
            )
            await self.session.flush()
            created.append(document)
            return document

        document = await get_or_create(
            self.session,
            lookup=lambda: self.documents.get_by_content_hash(content_hash),
            create=create,
        )
        # A concurrent writer may have won the race inside `get_or_create`; the loser gets
        # the winner's row and must neither rewrite the object nor claim the import.
        return document, not created

    async def _store_content(
        self, document: Document, spool: IO[bytes], content_type: str
    ) -> None:
        """Upload the spooled bytes and move the document to its final status (RF-C04)."""
        key = document_key(document.content_hash, document.filename)
        spool.seek(0)
        try:
            uri = await run_in_threadpool(
                self.storage.put_stream, key, spool, content_type
            )
        except Exception as error:  # noqa: BLE001 - any backend failure is the same story
            logger.exception("storing %s failed", key)
            document.status = DocumentStatus.FAILED
            document.error = str(error)
            await self.session.flush()
            return

        document.storage_uri = uri
        document.status = DocumentStatus.STORED
        document.error = None
        await self.session.flush()

    async def _record_provenance(
        self, document_id: uuid.UUID, connection_id: uuid.UUID, original_uri: str
    ) -> DocumentProvenance:
        """Attach an origin to a document, idempotently on the natural key.

        A duplicate upload adds a provenance to the existing document instead of a second
        document: that a file was found again, elsewhere or under another name, is
        information about its origins and not a new file.
        """

        async def create() -> DocumentProvenance:
            provenance = self.provenances.add(
                DocumentProvenance(
                    document_id=document_id,
                    connection_id=connection_id,
                    original_uri=original_uri,
                )
            )
            await self.session.flush()
            return provenance

        return await get_or_create(
            self.session,
            lookup=lambda: self.provenances.get_by_natural_key(
                document_id, connection_id, original_uri
            ),
            create=create,
        )

    @staticmethod
    def _spool_and_hash(
        stream: IO[bytes], max_bytes: int
    ) -> tuple[IO[bytes], str, int]:
        """Copy a stream into a spool while hashing it, refusing to exceed `max_bytes`.

        Blocking on purpose and meant to be called in a worker thread: it is the only
        place the whole file passes through the process.

        Returns:
            The spool positioned at zero, the hex sha-256 and the size in bytes.

        Raises:
            FileTooLargeError: As soon as the limit is passed, so an oversized upload is
                not fully consumed before being rejected.
        """
        digest = hashlib.sha256()
        size = 0
        spool = tempfile.SpooledTemporaryFile(max_size=_SPOOL_MAX_BYTES)
        try:
            while chunk := stream.read(_READ_CHUNK_BYTES):
                size += len(chunk)
                if size > max_bytes:
                    raise FileTooLargeError(size, max_bytes)
                digest.update(chunk)
                spool.write(chunk)
        except BaseException:
            spool.close()
            raise
        spool.seek(0)
        return spool, digest.hexdigest(), size
