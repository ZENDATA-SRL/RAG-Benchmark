from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from src.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page
from src.dependencies import SessionDep, StorageDep, WorkflowsDep
from src.pipelines.exceptions import InvalidConfigurationListError
from src.pipelines.schemas import (
    EmbeddingProfileCreate,
    EmbeddingProfileCreated,
    EmbeddingProfileRead,
    VectorStoreProfileRead,
    ChunkComparisonRead,
    ChunkComparisonSide,
    ChunkingConfigurationCompose,
    ChunkingConfigurationComposed,
    ChunkingConfigurationCoverage,
    ChunkingConfigurationCreate,
    ChunkingConfigurationCreated,
    ChunkingConfigurationExpanded,
    ChunkingConfigurationRead,
    ChunkingProfileCreate,
    ChunkingProfileCreated,
    ChunkingProfileRead,
    ChunkRead,
    ChunkResultRead,
    DocumentChunksRead,
    DocumentFailureRead,
    DocumentParseRead,
    IndexBuildAccepted,
    IndexBuildCreate,
    IndexBuildCreated,
    IndexBuildRead,
    MaterializationAccepted,
    MaterializationCreate,
    MaterializationDetail,
    MaterializationRead,
    ParsePageRead,
    ParsingProfileCreate,
    ParsingProfileCreated,
    ParsingProfileRead,
)
from src.pipelines.service import (
    ChunkingConfigurationService,
    ExpandedConfiguration,
    IndexBuildService,
    IndexCorpusService,
    InspectionService,
    MaterializationRunService,
    MaterializationService,
    ProfileService,
)

# Message attached whenever a get-or-create returned a pre-existing row. Deduplication is by
# the hash of the behaviour and the name is excluded from it, so without saying this
# the user is left wondering where the name they typed went.
_REUSED_DETAIL = (
    "an identical configuration already existed and was reused; the name you supplied was "
    "not applied, because profiles are deduplicated by their parameters and not by name"
)

parsing_profiles_router = APIRouter(prefix="/parsing-profiles", tags=["pipelines"])
chunking_profiles_router = APIRouter(prefix="/chunking-profiles", tags=["pipelines"])
embedding_profiles_router = APIRouter(prefix="/embedding-profiles", tags=["pipelines"])
vector_store_profiles_router = APIRouter(prefix="/vector-store-profiles", tags=["pipelines"])
configurations_router = APIRouter(prefix="/chunking-configurations", tags=["pipelines"])
materializations_router = APIRouter(prefix="/materializations", tags=["materializations"])
index_builds_router = APIRouter(prefix="/index-builds", tags=["index-builds"])
chunks_router = APIRouter(tags=["inspection"])


# --------------------------------------------------------------------------------------
# Profiles
# --------------------------------------------------------------------------------------


@parsing_profiles_router.post(
    "", response_model=ParsingProfileCreated, status_code=status.HTTP_201_CREATED
)
async def create_parsing_profile(
    payload: ParsingProfileCreate, session: SessionDep
) -> ParsingProfileCreated:
    """Create a parsing profile, or return the identical one that already exists."""
    profile, created = await ProfileService(session).get_or_create_parsing_profile(
        name=payload.name,
        component_version_id=payload.component_version_id,
        params=payload.params,
    )
    return ParsingProfileCreated(
        profile=ParsingProfileRead.model_validate(profile),
        created=created,
        detail=None if created else _REUSED_DETAIL,
    )


@parsing_profiles_router.get("", response_model=Page[ParsingProfileRead])
async def list_parsing_profiles(
    session: SessionDep,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> Page[ParsingProfileRead]:
    """List the parsing profiles."""
    profiles, total = await ProfileService(session).list_parsing_profiles(
        limit=limit, offset=offset
    )
    return Page[ParsingProfileRead].build(
        [ParsingProfileRead.model_validate(profile) for profile in profiles],
        total=total,
        limit=limit,
        offset=offset,
    )


@parsing_profiles_router.get("/{profile_id}", response_model=ParsingProfileRead)
async def get_parsing_profile(
    profile_id: uuid.UUID, session: SessionDep
) -> ParsingProfileRead:
    """Return a parsing profile by id."""
    profile = await ProfileService(session).get_parsing_profile(profile_id)
    return ParsingProfileRead.model_validate(profile)


@chunking_profiles_router.post(
    "", response_model=ChunkingProfileCreated, status_code=status.HTTP_201_CREATED
)
async def create_chunking_profile(
    payload: ChunkingProfileCreate, session: SessionDep
) -> ChunkingProfileCreated:
    """Create a chunking profile, or return the identical one that already exists (RF-P07)."""
    profile, created = await ProfileService(session).get_or_create_chunking_profile(
        name=payload.name,
        component_version_id=payload.component_version_id,
        strategy=payload.strategy,
        chunk_size=payload.chunk_size,
        overlap=payload.overlap,
        params=payload.params,
    )
    return ChunkingProfileCreated(
        profile=ChunkingProfileRead.model_validate(profile),
        created=created,
        detail=None if created else _REUSED_DETAIL,
    )


@chunking_profiles_router.get("", response_model=Page[ChunkingProfileRead])
async def list_chunking_profiles(
    session: SessionDep,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> Page[ChunkingProfileRead]:
    """List the chunking profiles."""
    profiles, total = await ProfileService(session).list_chunking_profiles(
        limit=limit, offset=offset
    )
    return Page[ChunkingProfileRead].build(
        [ChunkingProfileRead.model_validate(profile) for profile in profiles],
        total=total,
        limit=limit,
        offset=offset,
    )


@chunking_profiles_router.get("/{profile_id}", response_model=ChunkingProfileRead)
async def get_chunking_profile(
    profile_id: uuid.UUID, session: SessionDep
) -> ChunkingProfileRead:
    """Return a chunking profile by id."""
    profile = await ProfileService(session).get_chunking_profile(profile_id)
    return ChunkingProfileRead.model_validate(profile)


@embedding_profiles_router.post(
    "", response_model=EmbeddingProfileCreated, status_code=status.HTTP_201_CREATED
)
async def create_embedding_profile(
    payload: EmbeddingProfileCreate, session: SessionDep
) -> EmbeddingProfileCreated:
    """Create an embedding profile, or return the identical one that already exists."""
    profile, created = await ProfileService(session).get_or_create_embedding_profile(
        name=payload.name,
        component_version_id=payload.component_version_id,
        modality=payload.modality,
        dimensions=payload.dimensions,
        params=payload.params,
    )
    return EmbeddingProfileCreated(
        profile=EmbeddingProfileRead.model_validate(profile),
        created=created,
        detail=None if created else _REUSED_DETAIL,
    )
    
@embedding_profiles_router.get("", response_model=Page[EmbeddingProfileRead])
async def list_embedding_profiles(
    session: SessionDep,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> Page[EmbeddingProfileRead]:
    """List the embedding profiles."""
    profiles, total = await ProfileService(session).list_embedding_profiles(
        limit=limit, offset=offset)
    return Page[EmbeddingProfileRead].build(
        [EmbeddingProfileRead.model_validate(profile) for profile in profiles],
        total=total,
        limit=limit,
        offset=offset,
    )

# --------------------------------------------------------------------------------------
# Chunking configurations
# --------------------------------------------------------------------------------------


def _expanded(expanded: ExpandedConfiguration) -> ChunkingConfigurationExpanded:
    """Inline the two profiles of a configuration into its read model."""
    return ChunkingConfigurationExpanded(
        **ChunkingConfigurationRead.model_validate(expanded.configuration).model_dump(),
        parsing_profile=ParsingProfileRead.model_validate(expanded.parsing_profile),
        chunking_profile=ChunkingProfileRead.model_validate(expanded.chunking_profile),
    )


@configurations_router.post(
    "", response_model=ChunkingConfigurationCreated, status_code=status.HTTP_201_CREATED
)
async def create_chunking_configuration(
    payload: ChunkingConfigurationCreate, session: SessionDep
) -> ChunkingConfigurationCreated:
    """Pair a parsing and a chunking profile, reusing the pair if it already exists."""
    service = ChunkingConfigurationService(session)
    configuration, created = await service.get_or_create(
        parsing_profile_id=payload.parsing_profile_id,
        chunking_profile_id=payload.chunking_profile_id,
        name=payload.name,
    )
    return ChunkingConfigurationCreated(
        configuration=_expanded(await service.expand(configuration)),
        created=created,
        detail=None if created else _REUSED_DETAIL,
    )


@configurations_router.post(
    "/compose",
    response_model=ChunkingConfigurationComposed,
    status_code=status.HTTP_201_CREATED,
)
async def compose_chunking_configuration(
    payload: ChunkingConfigurationCompose, session: SessionDep
) -> ChunkingConfigurationComposed:
    """Create both profiles and their configuration in one call, for a single UI form."""
    composed = await ChunkingConfigurationService(session).compose(
        parsing_component_version_id=payload.parsing_component_version_id,
        parsing_params=payload.parsing_params,
        parsing_profile_name=payload.parsing_profile_name,
        chunking_component_version_id=payload.chunking_component_version_id,
        chunking_strategy=payload.chunking_strategy,
        chunk_size=payload.chunk_size,
        overlap=payload.overlap,
        chunking_params=payload.chunking_params,
        chunking_profile_name=payload.chunking_profile_name,
        name=payload.name,
    )
    return ChunkingConfigurationComposed(
        configuration=_expanded(composed.expanded),
        created=composed.configuration_created,
        parsing_profile_created=composed.parsing_profile_created,
        chunking_profile_created=composed.chunking_profile_created,
        detail=None if composed.configuration_created else _REUSED_DETAIL,
    )


@configurations_router.get("", response_model=Page[ChunkingConfigurationExpanded])
async def list_chunking_configurations(
    session: SessionDep,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> Page[ChunkingConfigurationExpanded]:
    """List the configurations with their profiles inlined, so a label costs one call."""
    configurations, total = await ChunkingConfigurationService(session).list_expanded(
        limit=limit, offset=offset
    )
    return Page[ChunkingConfigurationExpanded].build(
        [_expanded(configuration) for configuration in configurations],
        total=total,
        limit=limit,
        offset=offset,
    )


@configurations_router.get(
    "/{configuration_id}", response_model=ChunkingConfigurationExpanded
)
async def get_chunking_configuration(
    configuration_id: uuid.UUID, session: SessionDep
) -> ChunkingConfigurationExpanded:
    """Return a configuration with its profiles inlined."""
    service = ChunkingConfigurationService(session)
    configuration = await service.get(configuration_id)
    return _expanded(await service.expand(configuration))


@configurations_router.get(
    "/{configuration_id}/coverage", response_model=ChunkingConfigurationCoverage
)
async def get_chunking_configuration_coverage(
    configuration_id: uuid.UUID,
    session: SessionDep,
    corpus_id: uuid.UUID = Query(...),
) -> ChunkingConfigurationCoverage:
    """Report whether a configuration is materialised over a corpus, and how far."""
    coverage = await ChunkingConfigurationService(session).coverage(
        configuration_id, corpus_id
    )
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
# Materialisation
# --------------------------------------------------------------------------------------


@materializations_router.post(
    "", response_model=MaterializationAccepted, status_code=status.HTTP_202_ACCEPTED
)
async def start_materialization(
    payload: MaterializationCreate,
    session: SessionDep,
    workflows: WorkflowsDep,
) -> MaterializationAccepted:
    """Launch a materialisation, or report the run already doing the same work."""
    launch = await MaterializationService(session, workflows).start(
        chunking_configuration_id=payload.chunking_configuration_id,
        document_ids=payload.document_ids,
        corpus_id=payload.corpus_id,
        concurrency=payload.concurrency,
    )
    return MaterializationAccepted(
        **MaterializationRead.model_validate(launch.run).model_dump(),
        started=launch.started,
        detail=None
        if launch.started
        else "an identical materialisation was already running and is reported instead",
    )


@materializations_router.get("", response_model=Page[MaterializationRead])
async def list_materializations(
    session: SessionDep,
    corpus_id: uuid.UUID | None = Query(default=None),
    chunking_configuration_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> Page[MaterializationRead]:
    """List the materialisation history, newest first."""
    runs, total = await MaterializationRunService(session).list(
        corpus_id=corpus_id,
        chunking_configuration_id=chunking_configuration_id,
        limit=limit,
        offset=offset,
    )
    return Page[MaterializationRead].build(
        [MaterializationRead.model_validate(run) for run in runs],
        total=total,
        limit=limit,
        offset=offset,
    )


@materializations_router.get("/{run_id}", response_model=MaterializationDetail)
async def get_materialization(run_id: uuid.UUID, session: SessionDep) -> MaterializationDetail:
    """Return the progress of a run; polled every couple of seconds by the UI (RT-U05).

    Served entirely from the denormalised row, so following a run never depends on Temporal
    being reachable.
    """
    service = MaterializationRunService(session)
    run = await service.get(run_id)
    return MaterializationDetail(
        **MaterializationRead.model_validate(run).model_dump(),
        failures=[
            DocumentFailureRead(document_id=failure.document_id, error=failure.error)
            for failure in await service.failures(run)
        ],
    )


@materializations_router.post("/{run_id}/cancel", response_model=MaterializationRead)
async def cancel_materialization(
    run_id: uuid.UUID, session: SessionDep, workflows: WorkflowsDep
) -> MaterializationRead:
    """Cancel a running materialisation, recording `cancelled` as its reason."""
    run = await MaterializationService(session, workflows).cancel(run_id)
    return MaterializationRead.model_validate(run)


@index_builds_router.post("", response_model=IndexBuildCreated, status_code=status.HTTP_201_CREATED)
async def create_index_build(
    payload: IndexBuildCreate, session: SessionDep
) -> IndexBuildCreated:
    """Create an index build, or return the identical one that already exists."""
    index_build, created = await IndexBuildService(session).get_or_create_reporting(
        corpus_snapshot_id=payload.corpus_snapshot_id,
        chunking_configuration_id=payload.chunking_configuration_id,
        embedding_profile_id=payload.embedding_profile_id,
        vector_store_profile_id=payload.vector_store_profile_id,
        name=payload.name,
        external_index_ref=payload.external_index_ref,
    )
    return IndexBuildCreated(
        index_build=IndexBuildRead.model_validate(index_build),
        created=created,
        detail=None if created else _REUSED_DETAIL,
    )


@index_builds_router.post(
    "/{index_build_id}/start",
    response_model=IndexBuildAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_index_build(
    index_build_id: uuid.UUID, session: SessionDep, workflows: WorkflowsDep
) -> IndexBuildAccepted:
    """Launch indexing for a build, or report the run already doing the same work."""
    launch = await IndexCorpusService(session, workflows).start(index_build_id)
    return IndexBuildAccepted(
        **IndexBuildRead.model_validate(launch.build).model_dump(),
        started=launch.started,
        detail=None
        if launch.started
        else "an identical index build was already running and is reported instead",
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
    """List the chunks of a document under a configuration, in `ordinal` order (RF-P08)."""
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
router.include_router(parsing_profiles_router)
router.include_router(chunking_profiles_router)
router.include_router(configurations_router)
router.include_router(materializations_router)
router.include_router(chunks_router)
router.include_router(index_builds_router)
router.include_router(embedding_profiles_router)