from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.artifacts.models import Chunk, ChunkResult
from src.corpora.models import CorpusSnapshotDocument
from src.indexes.models import IndexBuild


class IndexBuildRepository:
    """Data access for `index_builds` and for the chunk set each build indexes."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, build: IndexBuild) -> IndexBuild:
        self.session.add(build)
        return build

    async def get_by_id(self, build_id: uuid.UUID) -> IndexBuild | None:
        return await self.session.get(IndexBuild, build_id)

    async def get_by_chain_fingerprint(
        self, chain_fingerprint: str
    ) -> IndexBuild | None:
        """Resolve a build by the fingerprint of its whole population chain."""
        stmt = select(IndexBuild).where(
            IndexBuild.chain_fingerprint == chain_fingerprint
        )
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

    async def list_chunks(
        self, index_build_id: uuid.UUID, *, limit: int = 1000, offset: int = 0
    ) -> Sequence[Chunk]:
        """Chunks that an index build indexes, in document order.

        This set is deliberately not materialised: it is the join of `chunks` and
        `chunk_results` restricted to the build's chunking configuration and to the
        documents frozen into its corpus snapshot.
        """
        stmt = (
            _restrict_to_build(
                select(Chunk).join(
                    ChunkResult, ChunkResult.id == Chunk.chunk_result_id
                ),
                index_build_id,
            )
            .order_by(ChunkResult.document_id, Chunk.ordinal)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.scalars(stmt)
        return result.all()

    async def count_chunks(self, index_build_id: uuid.UUID) -> int:
        """Chunk count of an index build, aggregated from `chunk_results.chunk_count`."""
        stmt = _restrict_to_build(
            select(func.coalesce(func.sum(ChunkResult.chunk_count), 0)).select_from(
                ChunkResult
            ),
            index_build_id,
        )
        return await self.session.scalar(stmt) or 0


def _restrict_to_build(stmt: Select[Any], index_build_id: uuid.UUID) -> Select[Any]:
    """Narrow a query over `chunk_results` to the chunk set of one index build.

    Shared by listing and counting so the two cannot disagree on which chunks belong to
    the build.
    """
    build = (
        select(
            IndexBuild.chunking_configuration_id.label("configuration_id"),
            IndexBuild.corpus_snapshot_id.label("snapshot_id"),
        )
        .where(IndexBuild.id == index_build_id)
        .subquery()
    )
    return stmt.join(
        build, build.c.configuration_id == ChunkResult.chunking_configuration_id
    ).join(
        CorpusSnapshotDocument,
        (CorpusSnapshotDocument.snapshot_id == build.c.snapshot_id)
        & (CorpusSnapshotDocument.document_id == ChunkResult.document_id),
    )
