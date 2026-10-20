from __future__ import annotations

import dataclasses
import uuid

from sqlalchemy import select
from src.corpora.repository import CorpusSnapshotRepository
from src.indexes.models import IndexBuild
from src.indexes.repository import IndexBuildRepository
from src.infrastructure.database.enums import TERMINAL_ARTIFACT_STATUSES, ArtifactStatus
from src.pipelines.exceptions import ProfileNotFoundError
from temporalio import activity

from temporal.config import activity_session


@dataclasses.dataclass
class IndexBuildResolved:
    """What an index build workflow needs to drive materialisation and embedding.

    Only identifiers and sizes: the documents of the snapshot are paged by the activities
    that need them, never carried here, so the payload stays the same size for any corpus.
    """

    index_build_id: str
    corpus_snapshot_id: str
    chunking_configuration_id: str
    embedding_profile_id: str
    composition_hash: str
    document_count: int


@activity.defn
async def resolve_index_build(index_build_id: str) -> IndexBuildResolved:
    """Load an index build and the size and composition of its snapshot."""
    build_id = uuid.UUID(index_build_id)
    async with activity_session() as session:
        build = await session.get(IndexBuild, build_id)
        if build is None:
            raise ProfileNotFoundError("index build", build_id)
        snapshot = await CorpusSnapshotRepository(session).get_by_id(
            build.corpus_snapshot_id
        )
        if snapshot is None:
            raise ProfileNotFoundError("corpus snapshot", build.corpus_snapshot_id)

        return IndexBuildResolved(
            index_build_id=str(build.id),
            corpus_snapshot_id=str(build.corpus_snapshot_id),
            chunking_configuration_id=str(build.chunking_configuration_id),
            embedding_profile_id=str(build.embedding_profile_id),
            composition_hash=snapshot.composition_hash,
            document_count=snapshot.document_count,
        )


@activity.defn
async def open_index_build(workflow_id: str, index_build_id: str) -> None:
    """Mark an index build as running and bind it to the workflow id (RT-O07)."""
    async with activity_session() as session:
        build = await session.get(IndexBuild, uuid.UUID(index_build_id))
        if build is None:
            raise ProfileNotFoundError("index build", index_build_id)

        if (
            build.status is ArtifactStatus.PENDING
            or build.status in TERMINAL_ARTIFACT_STATUSES
            and build.workflow_id == workflow_id
        ):
            build.status = ArtifactStatus.RUNNING
        build.workflow_id = workflow_id
        await session.flush()


@activity.defn
async def complete_index_build(workflow_id: str, failed: bool = False) -> None:
    """Mark an index build finished after the vectors are stored or the run aborts."""
    async with activity_session() as session:
        build = await session.scalar(
            select(IndexBuild).where(IndexBuild.workflow_id == workflow_id)
        )
        if build is None:
            return
        build.status = ArtifactStatus.FAILED if failed else ArtifactStatus.READY
        await session.flush()


@activity.defn
async def count_index_chunks(index_build_id: str) -> int:
    """Return how many chunks the build will embed."""
    async with activity_session() as session:
        return await IndexBuildRepository(session).count_chunks(
            uuid.UUID(index_build_id)
        )
