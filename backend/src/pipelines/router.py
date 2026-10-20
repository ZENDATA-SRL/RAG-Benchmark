from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from src.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page
from src.dependencies import SessionDep
from src.pipelines.constants import REUSED_DETAIL
from src.pipelines.schemas import (
    ChunkingConfigurationCompose,
    ChunkingConfigurationComposed,
    ChunkingConfigurationCreate,
    ChunkingConfigurationCreated,
    ChunkingConfigurationExpanded,
    ChunkingConfigurationRead,
    ChunkingProfileCreate,
    ChunkingProfileCreated,
    ChunkingProfileRead,
    EmbeddingProfileCreate,
    EmbeddingProfileCreated,
    EmbeddingProfileRead,
    ParsingProfileCreate,
    ParsingProfileCreated,
    ParsingProfileRead,
    VectorStoreProfileCreate,
    VectorStoreProfileCreated,
    VectorStoreProfileRead,
)
from src.pipelines.service import (
    ChunkingConfigurationService,
    ExpandedConfiguration,
    ProfileService,
)

parsing_profiles_router = APIRouter(prefix="/parsing-profiles", tags=["pipelines"])
chunking_profiles_router = APIRouter(prefix="/chunking-profiles", tags=["pipelines"])
embedding_profiles_router = APIRouter(prefix="/embedding-profiles", tags=["pipelines"])
vector_store_profiles_router = APIRouter(
    prefix="/vector-store-profiles", tags=["pipelines"]
)
configurations_router = APIRouter(prefix="/chunking-configurations", tags=["pipelines"])


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
        detail=None if created else REUSED_DETAIL,
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
        detail=None if created else REUSED_DETAIL,
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
        detail=None if created else REUSED_DETAIL,
    )


@embedding_profiles_router.get("", response_model=Page[EmbeddingProfileRead])
async def list_embedding_profiles(
    session: SessionDep,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> Page[EmbeddingProfileRead]:
    """List the embedding profiles."""
    profiles, total = await ProfileService(session).list_embedding_profiles(
        limit=limit, offset=offset
    )
    return Page[EmbeddingProfileRead].build(
        [EmbeddingProfileRead.model_validate(profile) for profile in profiles],
        total=total,
        limit=limit,
        offset=offset,
    )


@embedding_profiles_router.get("/{profile_id}", response_model=EmbeddingProfileRead)
async def get_embedding_profile(
    profile_id: uuid.UUID, session: SessionDep
) -> EmbeddingProfileRead:
    """Return one embedding profile."""
    profile = await ProfileService(session).get_embedding_profile(profile_id)
    return EmbeddingProfileRead.model_validate(profile)


@vector_store_profiles_router.post(
    "", response_model=VectorStoreProfileCreated, status_code=status.HTTP_201_CREATED
)
async def create_vector_store_profile(
    payload: VectorStoreProfileCreate, session: SessionDep
) -> VectorStoreProfileCreated:
    """Create a vector store profile, or return the identical one that already exists."""
    profile, created = await ProfileService(session).get_or_create_vector_store_profile(
        name=payload.name,
        component_version_id=payload.component_version_id,
        index_params=payload.index_params,
    )
    return VectorStoreProfileCreated(
        profile=VectorStoreProfileRead.model_validate(profile),
        created=created,
        detail=None if created else REUSED_DETAIL,
    )


@vector_store_profiles_router.get("", response_model=Page[VectorStoreProfileRead])
async def list_vector_store_profiles(
    session: SessionDep,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> Page[VectorStoreProfileRead]:
    """List the vector store profiles."""
    profiles, total = await ProfileService(session).list_vector_store_profiles(
        limit=limit, offset=offset
    )
    return Page[VectorStoreProfileRead].build(
        [VectorStoreProfileRead.model_validate(profile) for profile in profiles],
        total=total,
        limit=limit,
        offset=offset,
    )


@vector_store_profiles_router.get(
    "/{profile_id}", response_model=VectorStoreProfileRead
)
async def get_vector_store_profile(
    profile_id: uuid.UUID, session: SessionDep
) -> VectorStoreProfileRead:
    """Return one vector store profile."""
    profile = await ProfileService(session).get_vector_store_profile(profile_id)
    return VectorStoreProfileRead.model_validate(profile)


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
        detail=None if created else REUSED_DETAIL,
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
        detail=None if composed.configuration_created else REUSED_DETAIL,
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


router = APIRouter()
router.include_router(parsing_profiles_router)
router.include_router(chunking_profiles_router)
router.include_router(embedding_profiles_router)
router.include_router(vector_store_profiles_router)
router.include_router(configurations_router)
