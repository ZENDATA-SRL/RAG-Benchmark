from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from src.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page
from src.dependencies import SessionDep, WorkflowsDep
from src.indexes.schemas import (
    IndexBuildAccepted,
    IndexBuildCreate,
    IndexBuildCreated,
    IndexBuildDetail,
    IndexBuildRead,
)
from src.indexes.service import IndexBuildService, IndexCorpusService
from src.pipelines.constants import REUSED_DETAIL

router = APIRouter(prefix="/index-builds", tags=["index-builds"])


@router.post("", response_model=IndexBuildCreated, status_code=status.HTTP_201_CREATED)
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
        detail=None if created else REUSED_DETAIL,
    )


@router.get("", response_model=Page[IndexBuildRead])
async def list_index_builds(
    session: SessionDep,
    corpus_snapshot_id: uuid.UUID | None = None,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> Page[IndexBuildRead]:
    """List index builds, newest first, optionally over one corpus snapshot."""
    builds, total = await IndexBuildService(session).list(
        corpus_snapshot_id=corpus_snapshot_id, limit=limit, offset=offset
    )
    return Page[IndexBuildRead].build(
        [IndexBuildRead.model_validate(build) for build in builds],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{index_build_id}", response_model=IndexBuildDetail)
async def get_index_build(
    index_build_id: uuid.UUID, session: SessionDep
) -> IndexBuildDetail:
    """Return an index build with its status and chunk count."""
    build, chunk_count = await IndexBuildService(session).get_with_chunk_count(
        index_build_id
    )
    return IndexBuildDetail(
        **IndexBuildRead.model_validate(build).model_dump(), chunk_count=chunk_count
    )


@router.post(
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
