from __future__ import annotations

import uuid
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Header, Query, UploadFile
from fastapi.responses import StreamingResponse
from starlette.concurrency import iterate_in_threadpool

from src.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page
from src.dependencies import SessionDep, SettingsDep, StorageDep
from src.documents.schemas import (
    DocumentMetadataUpdate,
    DocumentRead,
    DocumentWithProvenancesRead,
    UploadResponse,
)
from src.documents.service import DocumentService
from src.documents.upload import assert_within_limit, run_upload
from src.infrastructure.database.enums import DocumentStatus
from src.sources.schemas import DocumentProvenanceRead

router = APIRouter(prefix="/documents", tags=["documents"])

# Read size of the download response; matches the spool loop of the ingest side.
_DOWNLOAD_CHUNK_BYTES = 1024 * 1024


@router.post("/upload", response_model=UploadResponse)
async def upload_documents(
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
    files: list[UploadFile] = File(...),
    corpus_id: uuid.UUID | None = Form(default=None),
    content_length: int | None = Header(default=None),
) -> UploadResponse:
    """Upload one or more documents, deduplicating by content and recording provenance."""
    assert_within_limit(content_length, settings)
    return await run_upload(
        files,
        session=session,
        storage=storage,
        settings=settings,
        corpus_id=corpus_id,
    )


@router.get("", response_model=Page[DocumentRead])
async def list_documents(
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
    status: DocumentStatus | None = Query(default=None),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> Page[DocumentRead]:
    """List the documents, optionally filtered by acquisition status."""
    documents, total = await DocumentService(session, storage, settings).list(
        status=status, limit=limit, offset=offset
    )
    return Page[DocumentRead].build(
        [DocumentRead.model_validate(document) for document in documents],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{document_id}", response_model=DocumentWithProvenancesRead)
async def get_document(
    document_id: uuid.UUID,
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
) -> DocumentWithProvenancesRead:
    """Return a document with the origins it was acquired from."""
    service = DocumentService(session, storage, settings)
    document = await service.get(document_id)
    provenances = await service.list_provenances(document_id)
    return DocumentWithProvenancesRead(
        **DocumentRead.model_validate(document).model_dump(),
        provenances=[
            DocumentProvenanceRead.model_validate(provenance) for provenance in provenances
        ],
    )


@router.patch("/{document_id}/metadata", response_model=DocumentRead)
async def set_document_metadata(
    document_id: uuid.UUID,
    payload: DocumentMetadataUpdate,
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
) -> DocumentRead:
    """Replace the metadata of a document, which becomes a retrieval filter."""
    document = await DocumentService(session, storage, settings).set_metadata(
        document_id, payload.metadata
    )
    return DocumentRead.model_validate(document)


@router.get("/{document_id}/content")
async def download_document(
    document_id: uuid.UUID,
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
) -> StreamingResponse:
    """Stream the original bytes of a document, for the native preview of the UI."""
    document, stream = await DocumentService(session, storage, settings).open_content(
        document_id
    )
    return StreamingResponse(
        # The storage body is a blocking network stream, so it is drained off the event
        # loop; without this a single large download would stall every other request.
        iterate_in_threadpool(iter(lambda: stream.read(_DOWNLOAD_CHUNK_BYTES), b"")),
        media_type=document.mime_type,
        headers={
            "Content-Length": str(document.size_bytes),
            "Content-Disposition": (
                f"inline; filename*=UTF-8''{quote(document.filename)}"
            ),
        },
    )
