from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Header, Query, UploadFile, status

from src.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page
from src.corpora.constants import SNAPSHOT_REUSED_DETAIL
from src.corpora.schemas import (
    CorpusCreate,
    CorpusDocumentRemoved,
    CorpusDocumentsAdd,
    CorpusDocumentsAdded,
    CorpusProgress,
    CorpusRead,
    CorpusSnapshotCreate,
    CorpusSnapshotCreated,
    CorpusSnapshotRead,
    CorpusUpdate,
)
from src.corpora.service import CorpusService, CorpusSnapshotService
from src.dependencies import SessionDep, SettingsDep, StorageDep
from src.documents.schemas import DocumentRead, UploadResponse
from src.documents.upload import assert_within_limit, run_upload
from src.infrastructure.database.enums import DocumentStatus

router = APIRouter(prefix="/corpora", tags=["corpora"])


@router.post("", response_model=CorpusRead, status_code=status.HTTP_201_CREATED)
async def create_corpus(payload: CorpusCreate, session: SessionDep) -> CorpusRead:
    """Create a corpus."""
    corpus = await CorpusService(session).create(payload.name, payload.description)
    return CorpusRead.model_validate(corpus)


@router.get("", response_model=Page[CorpusRead])
async def list_corpora(
    session: SessionDep,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> Page[CorpusRead]:
    """List the corpora."""
    corpora, total = await CorpusService(session).list(limit=limit, offset=offset)
    return Page[CorpusRead].build(
        [CorpusRead.model_validate(corpus) for corpus in corpora],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{corpus_id}", response_model=CorpusRead)
async def get_corpus(corpus_id: uuid.UUID, session: SessionDep) -> CorpusRead:
    """Return a corpus by id."""
    corpus = await CorpusService(session).get(corpus_id)
    return CorpusRead.model_validate(corpus)


@router.patch("/{corpus_id}", response_model=CorpusRead)
async def update_corpus(
    corpus_id: uuid.UUID, payload: CorpusUpdate, session: SessionDep
) -> CorpusRead:
    """Update the name or the description of a corpus."""
    corpus = await CorpusService(session).update(
        corpus_id, name=payload.name, description=payload.description
    )
    return CorpusRead.model_validate(corpus)


@router.delete("/{corpus_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_corpus(corpus_id: uuid.UUID, session: SessionDep) -> None:
    """Delete a corpus, refusing if snapshots were already frozen from it."""
    await CorpusService(session).delete(corpus_id)


@router.get("/{corpus_id}/documents", response_model=Page[DocumentRead])
async def list_corpus_documents(
    corpus_id: uuid.UUID,
    session: SessionDep,
    status_filter: DocumentStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> Page[DocumentRead]:
    """List the documents of a corpus with their acquisition status."""
    documents, total = await CorpusService(session).list_documents(
        corpus_id, status=status_filter, limit=limit, offset=offset
    )
    return Page[DocumentRead].build(
        [DocumentRead.model_validate(document) for document in documents],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/{corpus_id}/documents", response_model=CorpusDocumentsAdded)
async def add_corpus_documents(
    corpus_id: uuid.UUID, payload: CorpusDocumentsAdd, session: SessionDep
) -> CorpusDocumentsAdded:
    """Add documents that already exist to a corpus."""
    count = await CorpusService(session).add_documents(corpus_id, payload.document_ids)
    return CorpusDocumentsAdded(corpus_id=corpus_id, document_count=count)


@router.delete(
    "/{corpus_id}/documents/{document_id}", response_model=CorpusDocumentRemoved
)
async def remove_corpus_document(
    corpus_id: uuid.UUID, document_id: uuid.UUID, session: SessionDep
) -> CorpusDocumentRemoved:
    """Detach a document from a corpus, leaving the document and its snapshots intact."""
    await CorpusService(session).remove_document(corpus_id, document_id)
    return CorpusDocumentRemoved(corpus_id=corpus_id, document_id=document_id)


@router.get("/{corpus_id}/progress", response_model=CorpusProgress)
async def get_corpus_progress(
    corpus_id: uuid.UUID, session: SessionDep
) -> CorpusProgress:
    """Return the acquisition progress of a corpus, per document status."""
    by_status = await CorpusService(session).progress(corpus_id)
    return CorpusProgress(
        corpus_id=corpus_id, total=sum(by_status.values()), by_status=by_status
    )


@router.post(
    "/{corpus_id}/snapshots",
    response_model=CorpusSnapshotCreated,
    status_code=status.HTTP_201_CREATED,
)
async def create_corpus_snapshot(
    corpus_id: uuid.UUID, payload: CorpusSnapshotCreate, session: SessionDep
) -> CorpusSnapshotCreated:
    """Freeze a selection of documents, or return the snapshot with the same composition."""
    snapshot, created = await CorpusSnapshotService(session).get_or_create_reporting(
        corpus_id, payload.document_ids, label=payload.label
    )
    return CorpusSnapshotCreated(
        snapshot=CorpusSnapshotRead.model_validate(snapshot),
        created=created,
        detail=None if created else SNAPSHOT_REUSED_DETAIL,
    )


@router.get("/{corpus_id}/snapshots", response_model=Page[CorpusSnapshotRead])
async def list_corpus_snapshots(
    corpus_id: uuid.UUID,
    session: SessionDep,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> Page[CorpusSnapshotRead]:
    """List the snapshots frozen from a corpus, newest first."""
    snapshots, total = await CorpusSnapshotService(session).list(
        corpus_id, limit=limit, offset=offset
    )
    return Page[CorpusSnapshotRead].build(
        [CorpusSnapshotRead.model_validate(snapshot) for snapshot in snapshots],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{corpus_id}/snapshots/{snapshot_id}", response_model=CorpusSnapshotRead)
async def get_corpus_snapshot(
    corpus_id: uuid.UUID, snapshot_id: uuid.UUID, session: SessionDep
) -> CorpusSnapshotRead:
    """Return one snapshot of a corpus."""
    snapshot = await CorpusSnapshotService(session).get(corpus_id, snapshot_id)
    return CorpusSnapshotRead.model_validate(snapshot)


@router.get(
    "/{corpus_id}/snapshots/{snapshot_id}/documents", response_model=Page[DocumentRead]
)
async def list_corpus_snapshot_documents(
    corpus_id: uuid.UUID,
    snapshot_id: uuid.UUID,
    session: SessionDep,
    limit: int = Query(default=100, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> Page[DocumentRead]:
    """List the documents frozen into a snapshot."""
    documents, total = await CorpusSnapshotService(session).list_documents(
        corpus_id, snapshot_id, limit=limit, offset=offset
    )
    return Page[DocumentRead].build(
        [DocumentRead.model_validate(document) for document in documents],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/{corpus_id}/documents/upload", response_model=UploadResponse)
async def upload_corpus_documents(
    corpus_id: uuid.UUID,
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
    files: list[UploadFile] = File(...),
    content_length: int | None = Header(default=None),
) -> UploadResponse:
    """Upload documents straight into a corpus, in one request."""
    assert_within_limit(content_length, settings)
    # Validated before a single byte is spooled, so an unknown corpus is a 404 and not a
    # batch of orphan documents.
    await CorpusService(session).get(corpus_id)
    return await run_upload(
        files,
        session=session,
        storage=storage,
        settings=settings,
        corpus_id=corpus_id,
    )
