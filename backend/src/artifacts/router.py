from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from src.artifacts.exceptions import InvalidConfigurationListError
from src.artifacts.schemas import (
    ChunkComparisonRead,
    ChunkComparisonSide,
    ChunkingConfigurationCoverage,
    ChunkRead,
    ChunkResultRead,
    DocumentChunksRead,
    DocumentParseRead,
    ParsePageRead,
)
from src.artifacts.service import CoverageService, InspectionService
from src.core.pagination import MAX_LIMIT
from src.dependencies import SessionDep, StorageDep

# Coverage is served under the configuration it describes, but it is read from the
# per-document artefacts, which is why it lives in this module.
coverage_router = APIRouter(prefix="/chunking-configurations", tags=["pipelines"])
chunks_router = APIRouter(tags=["inspection"])


@coverage_router.get(
    "/{configuration_id}/coverage", response_model=ChunkingConfigurationCoverage
)
async def get_chunking_configuration_coverage(
    configuration_id: uuid.UUID,
    session: SessionDep,
    corpus_id: uuid.UUID = Query(...),
) -> ChunkingConfigurationCoverage:
    """Report whether a configuration is materialised over a corpus, and how far."""
    coverage = await CoverageService(session).coverage(configuration_id, corpus_id)
    return ChunkingConfigurationCoverage(
        chunking_configuration_id=configuration_id,
        corpus_id=corpus_id,
        total=coverage.total,
        ready=coverage.ready,
        failed=coverage.failed,
        missing=coverage.missing,
        is_complete=coverage.total > 0 and coverage.ready == coverage.total,
    )


# --------------------------------------------------------------------------------------
# Inspection
# --------------------------------------------------------------------------------------


@chunks_router.get("/documents/{document_id}/chunks", response_model=DocumentChunksRead)
async def list_document_chunks(
    document_id: uuid.UUID,
    session: SessionDep,
    storage: StorageDep,
    chunking_configuration_id: uuid.UUID = Query(...),
    limit: int = Query(default=100, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> DocumentChunksRead:
    """List the chunks of a document under a configuration, in `ordinal` order."""
    chunks, total, chunk_result = await InspectionService(session, storage).list_chunks(
        document_id=document_id,
        chunking_configuration_id=chunking_configuration_id,
        limit=limit,
        offset=offset,
    )
    return DocumentChunksRead(
        document_id=document_id,
        chunking_configuration_id=chunking_configuration_id,
        chunk_result=ChunkResultRead.model_validate(chunk_result),
        items=[ChunkRead.model_validate(chunk) for chunk in chunks],
        total=total,
        limit=limit,
        offset=offset,
    )


@chunks_router.get(
    "/documents/{document_id}/chunks/compare", response_model=ChunkComparisonRead
)
async def compare_document_chunks(
    document_id: uuid.UUID,
    session: SessionDep,
    storage: StorageDep,
    configurations: str = Query(..., description="Comma-separated configuration ids"),
    limit: int = Query(default=100, ge=1, le=MAX_LIMIT),
) -> ChunkComparisonRead:
    """Show the same document chunked under several configurations, side by side."""
    service = InspectionService(session, storage)
    sides = []
    for configuration_id in _configuration_ids(configurations):
        chunks, _, chunk_result = await service.list_chunks(
            document_id=document_id,
            chunking_configuration_id=configuration_id,
            limit=limit,
        )
        sides.append(
            ChunkComparisonSide(
                chunking_configuration_id=configuration_id,
                chunk_result=ChunkResultRead.model_validate(chunk_result),
                chunks=[ChunkRead.model_validate(chunk) for chunk in chunks],
            )
        )
    return ChunkComparisonRead(document_id=document_id, sides=sides)


@chunks_router.get("/chunk-results", response_model=ChunkResultRead)
async def get_chunk_result(
    session: SessionDep,
    storage: StorageDep,
    document_id: uuid.UUID = Query(...),
    chunking_configuration_id: uuid.UUID = Query(...),
) -> ChunkResultRead:
    """Return the state of a chunking artefact, which is where that state lives."""
    chunk_result = await InspectionService(session, storage).get_chunk_result(
        document_id=document_id, chunking_configuration_id=chunking_configuration_id
    )
    return ChunkResultRead.model_validate(chunk_result)


@chunks_router.get("/chunks/{chunk_id}", response_model=ChunkRead)
async def get_chunk(
    chunk_id: uuid.UUID, session: SessionDep, storage: StorageDep
) -> ChunkRead:
    """Return a single chunk, for the side panel of the UI."""
    chunk = await InspectionService(session, storage).get_chunk(chunk_id)
    return ChunkRead.model_validate(chunk)


@chunks_router.get("/documents/{document_id}/parse", response_model=DocumentParseRead)
async def get_document_parse(
    document_id: uuid.UUID,
    session: SessionDep,
    storage: StorageDep,
    parsing_profile_id: uuid.UUID = Query(...),
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> DocumentParseRead:
    """Return the parsed text of a document, page by page, to diagnose a strange chunking."""
    pages, total, result = await InspectionService(session, storage).parse_pages(
        document_id=document_id,
        parsing_profile_id=parsing_profile_id,
        limit=limit,
        offset=offset,
    )
    return DocumentParseRead(
        document_id=document_id,
        parsing_profile_id=parsing_profile_id,
        parsing_result_id=result.id,
        status=result.status,
        items=[ParsePageRead(page=page.page, text=page.text) for page in pages],
        total=total,
        limit=limit,
        offset=offset,
    )


def _configuration_ids(raw: str) -> list[uuid.UUID]:
    """Parse the comma-separated `configurations` query parameter.

    Duplicates are dropped so comparing a configuration with itself cannot pad the response
    with identical columns.

    Raises:
        InvalidConfigurationListError: If any element is not a UUID, so a typo is a 422 with
            the offending value rather than a 500.
    """
    try:
        parsed = [uuid.UUID(part.strip()) for part in raw.split(",") if part.strip()]
    except ValueError as error:
        raise InvalidConfigurationListError(raw) from error
    if not parsed:
        raise InvalidConfigurationListError(raw)
    return list(dict.fromkeys(parsed))


router = APIRouter()
router.include_router(coverage_router)
router.include_router(chunks_router)
