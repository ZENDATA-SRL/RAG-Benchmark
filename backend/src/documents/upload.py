from __future__ import annotations

import uuid
from collections.abc import Sequence

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.corpora.service import CorpusService
from src.documents.exceptions import FileTooLargeError
from src.documents.schemas import UploadFileResult, UploadResponse
from src.documents.service import DocumentService, UploadCandidate, UploadOutcome
from src.infrastructure.database.enums import FileOutcome
from src.infrastructure.storage import ObjectStorage
from src.settings import Settings
from src.sources.service import UploadImportService

# MIME type assumed when the client sends none; the allow-list rejects it, which is the
# right outcome for a file whose type nobody declared.
_FALLBACK_CONTENT_TYPE = "application/octet-stream"


async def run_upload(
    files: Sequence[UploadFile],
    *,
    session: AsyncSession,
    storage: ObjectStorage,
    settings: Settings,
    corpus_id: uuid.UUID | None = None,
) -> UploadResponse:
    """Ingest an upload request as one import run, optionally filing it into a corpus.

    Shared by `POST /documents/upload` and the corpus shortcut so the two endpoints cannot
    disagree on what an upload records.

    Args:
        files: Files of the multipart request.
        session: Session owning the transaction.
        storage: Object storage the content is written to.
        settings: Limits and allow-list applied to each file.
        corpus_id: Corpus the imported documents are added to, when given. The corpus must
            already have been validated by the caller.

    Returns:
        The per-file outcomes and their aggregate, together with the import run id.
    """
    imports = UploadImportService(session)
    documents = DocumentService(session, storage, settings)

    run = await imports.open_run()
    connection_id = await _connection_of(imports)

    outcomes = await documents.ingest_upload_batch(
        [_to_candidate(upload) for upload in files], connection_id=connection_id
    )

    for outcome in outcomes:
        imports.record_file_result(
            run,
            source_uri=outcome.filename,
            outcome=outcome.outcome,
            document_id=outcome.document_id,
            error_reason=outcome.error_reason,
        )

    if corpus_id is not None:
        await _add_to_corpus(session, corpus_id, outcomes)

    await imports.close_run(run)

    return UploadResponse(
        import_run_id=run.id,
        results=[
            UploadFileResult(
                filename=outcome.filename,
                outcome=outcome.outcome,
                document_id=outcome.document_id,
                error_reason=outcome.error_reason,
            )
            for outcome in outcomes
        ],
        counts={str(key): value for key, value in run.counts.items()},
    )


def assert_within_limit(content_length: int | None, settings: Settings) -> None:
    """Reject an oversized request before its body is read.

    Checked on the declared length so a 2 GB body is refused at the first bytes instead of
    being spooled to disk only to be discarded. The per-file limit still applies
    afterwards, because `Content-Length` covers the whole multipart envelope and a client
    is free not to send it.

    Raises:
        FileTooLargeError: If the declared size already exceeds `max_upload_bytes`.
    """
    if content_length is not None and content_length > settings.max_upload_bytes:
        raise FileTooLargeError(content_length, settings.max_upload_bytes)


def _to_candidate(upload: UploadFile) -> UploadCandidate:
    """Adapt a FastAPI upload to what the service consumes."""
    return UploadCandidate(
        filename=upload.filename or "unnamed",
        content_type=upload.content_type or _FALLBACK_CONTENT_TYPE,
        stream=upload.file,
    )


async def _connection_of(imports: UploadImportService) -> uuid.UUID:
    """Return the connection manual uploads are attributed to."""
    selection = await imports.get_or_create_selection()
    return selection.connection_id


async def _add_to_corpus(
    session: AsyncSession, corpus_id: uuid.UUID, outcomes: Sequence[UploadOutcome]
) -> None:
    """File the documents of a batch into a corpus.

    Duplicates are included: the file was already known but the user asked for it in *this*
    corpus, and membership is not what deduplication is about.
    """
    document_ids = [
        outcome.document_id
        for outcome in outcomes
        if outcome.document_id is not None
        and outcome.outcome in (FileOutcome.IMPORTED, FileOutcome.SKIPPED_DUPLICATE)
    ]
    if document_ids:
        await CorpusService(session).add_documents(corpus_id, document_ids)
