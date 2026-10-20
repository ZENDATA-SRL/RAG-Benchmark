from __future__ import annotations

import dataclasses
import uuid

from sqlalchemy import select
from src.corpora.repository import CorpusSnapshotRepository
from src.infrastructure.database.enums import ArtifactStatus
from src.pipelines.exceptions import ProfileNotFoundError
from src.pipelines.models import IndexBuild
from src.pipelines.repository import ChunkRepository
from src.pipelines.service import TERMINAL_ARTIFACT_STATUSES
from temporalio import activity

from temporal.config import activity_session


@dataclasses.dataclass
class IndexBuildResolved:
    """What an index build workflow needs to drive materialisation and embedding."""

    index_build_id: str
    corpus_snapshot_id: str
    chunking_configuration_id: str
    embedding_profile_id: str
    document_ids: list[str]


@dataclasses.dataclass
class ChunkForEmbedding:
    """One chunk passed to the embedder."""

    chunk_id: str
    text: str


@dataclasses.dataclass
class ChunkBatch:
    """A page of chunks belonging to an index build."""

    chunks: list[ChunkForEmbedding]


@activity.defn
async def resolve_index_build(index_build_id: str) -> IndexBuildResolved:
    """Load an index build and the document ids frozen into its snapshot."""
    build_id = uuid.UUID(index_build_id)
    async with activity_session() as session:
        build = await session.get(IndexBuild, build_id)
        if build is None:
            raise ProfileNotFoundError("index build", build_id)

        snapshots = CorpusSnapshotRepository(session)
        total = await snapshots.count_snapshot_documents(build.corpus_snapshot_id)
        document_ids: list[str] = []
        offset = 0
        page_size = 1000
        while offset < total:
            documents = await snapshots.list_snapshot_documents(
                build.corpus_snapshot_id, limit=page_size, offset=offset
            )
            document_ids.extend(str(document.id) for document in documents)
            offset += page_size

        return IndexBuildResolved(
            index_build_id=str(build.id),
            corpus_snapshot_id=str(build.corpus_snapshot_id),
            chunking_configuration_id=str(build.chunking_configuration_id),
            embedding_profile_id=str(build.embedding_profile_id),
            document_ids=document_ids,
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
    """Mark an index build finished after embedding completes or the run aborts."""
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
        return await ChunkRepository(session).count_for_index_build(uuid.UUID(index_build_id))


@activity.defn
async def fetch_index_chunk_batch(
    index_build_id: str, offset: int, limit: int
) -> ChunkBatch:
    """Return the next page of chunk text to embed for an index build."""
    async with activity_session() as session:
        chunks = await ChunkRepository(session).list_for_index_build(
            uuid.UUID(index_build_id), limit=limit, offset=offset
        )
        return ChunkBatch(
            chunks=[
                ChunkForEmbedding(chunk_id=str(chunk.id), text=chunk.text)
                for chunk in chunks
            ]
        )
