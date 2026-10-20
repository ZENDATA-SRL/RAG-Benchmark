from __future__ import annotations

import dataclasses
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.get_or_create import get_or_create_reporting
from src.core.hashing import chain_fingerprint
from src.corpora.repository import CorpusSnapshotRepository
from src.indexes.exceptions import IndexBuildNotFoundError
from src.indexes.models import IndexBuild
from src.indexes.repository import IndexBuildRepository
from src.infrastructure.database.enums import TERMINAL_ARTIFACT_STATUSES, ArtifactStatus
from src.infrastructure.temporal import WorkflowClient
from src.infrastructure.temporal.workflow_ids import (
    CHUNKING_TASK_QUEUE,
    INDEX_CORPUS_WORKFLOW,
    index_corpus_workflow_id,
)
from src.pipelines.exceptions import ProfileNotFoundError
from src.pipelines.models import EmbeddingProfile, VectorStoreProfile
from src.pipelines.repository import ChunkingConfigurationRepository, ProfileRepository


class IndexBuildService:
    """The vector DB population configuration."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.builds = IndexBuildRepository(session)
        self.snapshots = CorpusSnapshotRepository(session)
        self.configurations = ChunkingConfigurationRepository(session)
        self.embedding_profiles = ProfileRepository(session, EmbeddingProfile)
        self.vector_store_profiles = ProfileRepository(session, VectorStoreProfile)

    async def get(self, index_build_id: uuid.UUID) -> IndexBuild:
        """Return an index build by id.

        Raises:
            IndexBuildNotFoundError: If it does not exist.
        """
        build = await self.builds.get_by_id(index_build_id)
        if build is None:
            raise IndexBuildNotFoundError(index_build_id)
        return build

    async def get_or_create(
        self,
        *,
        corpus_snapshot_id: uuid.UUID,
        chunking_configuration_id: uuid.UUID,
        embedding_profile_id: uuid.UUID,
        vector_store_profile_id: uuid.UUID,
        name: str | None = None,
        external_index_ref: str | None = None,
    ) -> IndexBuild:
        """Return the index build for a whole population chain, creating it once."""
        build, _created = await self.get_or_create_reporting(
            corpus_snapshot_id=corpus_snapshot_id,
            chunking_configuration_id=chunking_configuration_id,
            embedding_profile_id=embedding_profile_id,
            vector_store_profile_id=vector_store_profile_id,
            name=name,
            external_index_ref=external_index_ref,
        )
        return build

    async def get_or_create_reporting(
        self,
        *,
        corpus_snapshot_id: uuid.UUID,
        chunking_configuration_id: uuid.UUID,
        embedding_profile_id: uuid.UUID,
        vector_store_profile_id: uuid.UUID,
        name: str | None = None,
        external_index_ref: str | None = None,
    ) -> tuple[IndexBuild, bool]:
        """Return an index build and whether this call created it.

        The fingerprint covers snapshot composition, chunking configuration, embedder and
        vector store, i.e. everything the content of the index depends on, so repeating
        the same choice rebuilds nothing and stays comparable with what was measured
        before.

        Raises:
            ProfileNotFoundError: If any referenced entity does not exist.
        """
        snapshot = await self.snapshots.get_by_id(corpus_snapshot_id)
        if snapshot is None:
            raise ProfileNotFoundError("corpus snapshot", corpus_snapshot_id)
        configuration = await self.configurations.get_by_id(chunking_configuration_id)
        if configuration is None:
            raise ProfileNotFoundError(
                "chunking configuration", chunking_configuration_id
            )
        embedding = await self.embedding_profiles.get_by_id(embedding_profile_id)
        if embedding is None:
            raise ProfileNotFoundError("embedding", embedding_profile_id)
        vector_store = await self.vector_store_profiles.get_by_id(
            vector_store_profile_id
        )
        if vector_store is None:
            raise ProfileNotFoundError("vector store", vector_store_profile_id)

        fingerprint = chain_fingerprint(
            snapshot.composition_hash,
            configuration.config_hash,
            embedding.config_hash,
            vector_store.config_hash,
        )
        label = name or f"{snapshot.label} · {configuration.name} · {embedding.name}"

        async def create() -> IndexBuild:
            build = self.builds.add(
                IndexBuild(
                    name=label,
                    corpus_snapshot_id=corpus_snapshot_id,
                    chunking_configuration_id=chunking_configuration_id,
                    embedding_profile_id=embedding_profile_id,
                    vector_store_profile_id=vector_store_profile_id,
                    chain_fingerprint=fingerprint,
                    external_index_ref=external_index_ref or f"idx_{fingerprint[:16]}",
                )
            )
            await self.session.flush()
            return build

        return await get_or_create_reporting(
            self.session,
            lookup=lambda: self.builds.get_by_chain_fingerprint(fingerprint),
            create=create,
        )


@dataclasses.dataclass(frozen=True)
class IndexBuildLaunch:
    """An index build workflow launch and whether this request started it."""

    build: IndexBuild
    started: bool


class IndexCorpusService:
    """Launch the chunk materialisation and embedding workflow for an index build."""

    def __init__(self, session: AsyncSession, workflows: WorkflowClient) -> None:
        self.session = session
        self.workflows = workflows
        self.builds = IndexBuildService(session)

    async def start(self, index_build_id: uuid.UUID) -> IndexBuildLaunch:
        """Start indexing for a build, or report the run already doing the same work.

        The workflow id is a function of the index build id, so a second identical request
        is refused by Temporal itself and reported as the existing run (RT-O01).
        """
        build = await self.builds.get(index_build_id)
        workflow_id = index_corpus_workflow_id(index_build_id)

        if build.status is ArtifactStatus.PENDING or (
            build.status in TERMINAL_ARTIFACT_STATUSES
            and build.workflow_id == workflow_id
        ):
            build.status = ArtifactStatus.RUNNING
        build.workflow_id = workflow_id
        await self.session.flush()

        outcome = await self.workflows.start(
            INDEX_CORPUS_WORKFLOW,
            arg=str(index_build_id),
            workflow_id=workflow_id,
            task_queue=CHUNKING_TASK_QUEUE,
        )
        return IndexBuildLaunch(build=build, started=outcome.started)
