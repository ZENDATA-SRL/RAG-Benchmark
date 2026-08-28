from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from typing import Generic, TypeVar

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.corpora.models import CorpusSnapshotDocument
from src.pipelines.models import (
    Chunk,
    ChunkingConfiguration,
    ChunkingProfile,
    ChunkResult,
    EmbeddingProfile,
    IndexBuild,
    MaterializationRun,
    ParsingProfile,
    ParsingResult,
    RetrievalProfile,
    VectorStoreProfile,
)

# The five profiles share the same `config_hash` dedup key, so their data access is one
# generic class parametrised by model rather than five near-identical copies.
ProfileT = TypeVar(
    "ProfileT",
    ParsingProfile,
    ChunkingProfile,
    EmbeddingProfile,
    VectorStoreProfile,
    RetrievalProfile,
)


class ProfileRepository(Generic[ProfileT]):
    """Data access for a pipeline profile table, keyed by `config_hash`."""

    def __init__(self, session: AsyncSession, model: type[ProfileT]) -> None:
        self.session = session
        self.model = model

    def add(self, profile: ProfileT) -> ProfileT:
        self.session.add(profile)
        return profile

    async def get_by_id(self, profile_id: uuid.UUID) -> ProfileT | None:
        return await self.session.get(self.model, profile_id)

    async def get_by_config_hash(self, config_hash: str) -> ProfileT | None:
        """Look up a profile by its content-addressed dedup key."""
        stmt = select(self.model).where(self.model.config_hash == config_hash)
        return await self.session.scalar(stmt)

    async def list(self, *, limit: int = 50, offset: int = 0) -> Sequence[ProfileT]:
        stmt = select(self.model).order_by(self.model.name).limit(limit).offset(offset)
        result = await self.session.scalars(stmt)
        return result.all()


class ChunkingConfigurationRepository:
    """Data access for `chunking_configurations`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, configuration: ChunkingConfiguration) -> ChunkingConfiguration:
        self.session.add(configuration)
        return configuration

    async def get_by_id(self, configuration_id: uuid.UUID) -> ChunkingConfiguration | None:
        return await self.session.get(ChunkingConfiguration, configuration_id)

    async def get_by_config_hash(self, config_hash: str) -> ChunkingConfiguration | None:
        stmt = select(ChunkingConfiguration).where(
            ChunkingConfiguration.config_hash == config_hash
        )
        return await self.session.scalar(stmt)

    async def get_by_profiles(
        self, parsing_profile_id: uuid.UUID, chunking_profile_id: uuid.UUID
    ) -> ChunkingConfiguration | None:
        """Look up the configuration for a (parsing, chunking) profile pair."""
        stmt = select(ChunkingConfiguration).where(
            ChunkingConfiguration.parsing_profile_id == parsing_profile_id,
            ChunkingConfiguration.chunking_profile_id == chunking_profile_id,
        )
        return await self.session.scalar(stmt)

    async def list(self, *, limit: int = 50, offset: int = 0) -> Sequence[ChunkingConfiguration]:
        stmt = (
            select(ChunkingConfiguration)
            .order_by(ChunkingConfiguration.name)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.scalars(stmt)
        return result.all()


class ParsingResultRepository:
    """Data access for `parsing_results`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, result: ParsingResult) -> ParsingResult:
        self.session.add(result)
        return result

    async def get_by_id(self, result_id: uuid.UUID) -> ParsingResult | None:
        return await self.session.get(ParsingResult, result_id)

    async def get_by_cache_key(self, cache_key: str) -> ParsingResult | None:
        """Resolve the cache entry of a (document, parsing profile) pair."""
        stmt = select(ParsingResult).where(ParsingResult.cache_key == cache_key)
        return await self.session.scalar(stmt)

    async def list_by_documents(
        self, document_ids: Sequence[uuid.UUID], parsing_profile_id: uuid.UUID
    ) -> Sequence[ParsingResult]:
        """Batch lookup of the parses of many documents under one profile."""
        if not document_ids:
            return []
        stmt = select(ParsingResult).where(
            ParsingResult.document_id.in_(document_ids),
            ParsingResult.parsing_profile_id == parsing_profile_id,
        )
        result = await self.session.scalars(stmt)
        return result.all()


class ChunkResultRepository:
    """Data access for `chunk_results`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, result: ChunkResult) -> ChunkResult:
        self.session.add(result)
        return result

    async def get_by_id(self, result_id: uuid.UUID) -> ChunkResult | None:
        return await self.session.get(ChunkResult, result_id)

    async def get_by_cache_key(self, cache_key: str) -> ChunkResult | None:
        """Resolve the cache entry of a (document, chunking configuration) pair."""
        stmt = select(ChunkResult).where(ChunkResult.cache_key == cache_key)
        return await self.session.scalar(stmt)

    async def list_by_documents(
        self, document_ids: Sequence[uuid.UUID], chunking_configuration_id: uuid.UUID
    ) -> Sequence[ChunkResult]:
        """Batch lookup used to decide which documents still need chunking."""
        if not document_ids:
            return []
        stmt = select(ChunkResult).where(
            ChunkResult.document_id.in_(document_ids),
            ChunkResult.chunking_configuration_id == chunking_configuration_id,
        )
        result = await self.session.scalars(stmt)
        return result.all()


class ChunkRepository:
    """Data access for `chunks`, including the chunk set of an index build."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add_all(self, chunks: Iterable[Chunk]) -> None:
        self.session.add_all(list(chunks))

    async def delete_by_chunk_result(self, chunk_result_id: uuid.UUID) -> int:
        """Delete the chunks of a chunk result, returning how many were removed.

        Used before rewriting the chunks of a `failed` result: without clearing the
        orphans of the previous attempt, the unique `(chunk_result_id, ordinal)` would make
        the retry fail on the first re-inserted ordinal.
        """
        result = await self.session.execute(
            delete(Chunk).where(Chunk.chunk_result_id == chunk_result_id)
        )
        return result.rowcount or 0

    async def get_by_id(self, chunk_id: uuid.UUID) -> Chunk | None:
        return await self.session.get(Chunk, chunk_id)

    async def list_by_chunk_result(
        self, chunk_result_id: uuid.UUID, *, limit: int = 100, offset: int = 0
    ) -> Sequence[Chunk]:
        """Chunks of one document under one configuration, in document order."""
        stmt = (
            select(Chunk)
            .where(Chunk.chunk_result_id == chunk_result_id)
            .order_by(Chunk.ordinal)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.scalars(stmt)
        return result.all()

    async def list_for_index_build(
        self, index_build_id: uuid.UUID, *, limit: int = 1000, offset: int = 0
    ) -> Sequence[Chunk]:
        """Chunks that an index build indexes.

        This set is deliberately not materialised (§6.3): it is the join of `chunks` and
        `chunk_results` restricted to the build's chunking configuration and to the
        documents frozen into its corpus snapshot.
        """
        build = select(
            IndexBuild.chunking_configuration_id.label("configuration_id"),
            IndexBuild.corpus_snapshot_id.label("snapshot_id"),
        ).where(IndexBuild.id == index_build_id).subquery()

        stmt = (
            select(Chunk)
            .join(ChunkResult, ChunkResult.id == Chunk.chunk_result_id)
            .join(build, build.c.configuration_id == ChunkResult.chunking_configuration_id)
            .join(
                CorpusSnapshotDocument,
                (CorpusSnapshotDocument.snapshot_id == build.c.snapshot_id)
                & (CorpusSnapshotDocument.document_id == ChunkResult.document_id),
            )
            .order_by(ChunkResult.document_id, Chunk.ordinal)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.scalars(stmt)
        return result.all()

    async def count_for_index_build(self, index_build_id: uuid.UUID) -> int:
        """Chunk count of an index build, aggregated from `chunk_results.chunk_count`."""
        build = select(
            IndexBuild.chunking_configuration_id.label("configuration_id"),
            IndexBuild.corpus_snapshot_id.label("snapshot_id"),
        ).where(IndexBuild.id == index_build_id).subquery()

        stmt = (
            select(func.coalesce(func.sum(ChunkResult.chunk_count), 0))
            .select_from(ChunkResult)
            .join(build, build.c.configuration_id == ChunkResult.chunking_configuration_id)
            .join(
                CorpusSnapshotDocument,
                (CorpusSnapshotDocument.snapshot_id == build.c.snapshot_id)
                & (CorpusSnapshotDocument.document_id == ChunkResult.document_id),
            )
        )
        return await self.session.scalar(stmt) or 0


class IndexBuildRepository:
    """Data access for `index_builds`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, build: IndexBuild) -> IndexBuild:
        self.session.add(build)
        return build

    async def get_by_id(self, build_id: uuid.UUID) -> IndexBuild | None:
        return await self.session.get(IndexBuild, build_id)

    async def get_by_chain_fingerprint(self, chain_fingerprint: str) -> IndexBuild | None:
        """Resolve a build by the fingerprint of its whole population chain."""
        stmt = select(IndexBuild).where(IndexBuild.chain_fingerprint == chain_fingerprint)
        return await self.session.scalar(stmt)

    async def get_by_workflow_id(self, workflow_id: str) -> IndexBuild | None:
        stmt = select(IndexBuild).where(IndexBuild.workflow_id == workflow_id)
        return await self.session.scalar(stmt)

    async def list_by_snapshot(
        self, corpus_snapshot_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> Sequence[IndexBuild]:
        """Builds over one search space: the candidates an experiment picks from."""
        stmt = (
            select(IndexBuild)
            .where(IndexBuild.corpus_snapshot_id == corpus_snapshot_id)
            .order_by(IndexBuild.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.scalars(stmt)
        return result.all()


class MaterializationRunRepository:
    """Data access for `materialization_runs`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, run: MaterializationRun) -> MaterializationRun:
        self.session.add(run)
        return run

    async def get_by_id(self, run_id: uuid.UUID) -> MaterializationRun | None:
        return await self.session.get(MaterializationRun, run_id)

    async def get_by_workflow_id(self, workflow_id: str) -> MaterializationRun | None:
        """Resolve a run by its deterministic Temporal workflow id (RT-O01)."""
        stmt = select(MaterializationRun).where(
            MaterializationRun.workflow_id == workflow_id
        )
        return await self.session.scalar(stmt)
