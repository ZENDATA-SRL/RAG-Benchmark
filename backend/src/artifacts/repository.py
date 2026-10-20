from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.artifacts.models import Chunk, ChunkResult, ParsingResult
from src.infrastructure.database.enums import ArtifactStatus


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

    async def get_by_document_and_profile(
        self, document_id: uuid.UUID, parsing_profile_id: uuid.UUID
    ) -> ParsingResult | None:
        """Resolve a parse by the pair it belongs to, without recomputing its cache key.

        The cache key needs the document's content hash and the profile's config hash; a
        reader that only has the two ids would have to load both rows first, so the unique
        `(document_id, parsing_profile_id)` is queried directly instead.
        """
        stmt = select(ParsingResult).where(
            ParsingResult.document_id == document_id,
            ParsingResult.parsing_profile_id == parsing_profile_id,
        )
        return await self.session.scalar(stmt)


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

    async def get_by_document_and_configuration(
        self, document_id: uuid.UUID, chunking_configuration_id: uuid.UUID
    ) -> ChunkResult | None:
        """Resolve a chunk result by the pair it belongs to, without its cache key.

        Backed by the unique `(document_id, chunking_configuration_id)`: this is the lookup
        the inspection endpoints do, and they hold the two ids and nothing else.
        """
        stmt = select(ChunkResult).where(
            ChunkResult.document_id == document_id,
            ChunkResult.chunking_configuration_id == chunking_configuration_id,
        )
        return await self.session.scalar(stmt)

    async def count_by_status(
        self, document_ids: Sequence[uuid.UUID], chunking_configuration_id: uuid.UUID
    ) -> dict[ArtifactStatus, int]:
        """Group the chunk results of a document set by status, for coverage.

        Aggregated in SQL rather than by loading the rows: coverage is asked for a whole
        corpus, and the caller only ever needs the counts.
        """
        if not document_ids:
            return {}
        stmt = (
            select(ChunkResult.status, func.count())
            .where(
                ChunkResult.document_id.in_(document_ids),
                ChunkResult.chunking_configuration_id == chunking_configuration_id,
            )
            .group_by(ChunkResult.status)
        )
        rows = await self.session.execute(stmt)
        return {status: count for status, count in rows.all()}

    async def list_failed(
        self,
        chunking_configuration_id: uuid.UUID,
        *,
        document_ids: Sequence[uuid.UUID] | None = None,
        limit: int = 50,
    ) -> Sequence[ChunkResult]:
        """Failed chunk results of a configuration, to explain a run's failures (RT-O07).

        `document_ids` narrows the set to a corpus; omitted, the whole configuration is
        considered, which is what a run launched on explicit ids needs.
        """
        stmt = select(ChunkResult).where(
            ChunkResult.chunking_configuration_id == chunking_configuration_id,
            ChunkResult.status == ArtifactStatus.FAILED,
        )
        if document_ids is not None:
            if not document_ids:
                return []
            stmt = stmt.where(ChunkResult.document_id.in_(document_ids))
        stmt = stmt.order_by(ChunkResult.created_at).limit(limit)
        result = await self.session.scalars(stmt)
        return result.all()


class ChunkRepository:
    """Data access for `chunks`."""

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
            delete(Chunk)
            .where(Chunk.chunk_result_id == chunk_result_id)
            .returning(Chunk.id)
        )
        return len(result.all())

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

    async def count_by_chunk_result(self, chunk_result_id: uuid.UUID) -> int:
        """Chunks actually stored for a result, counted rather than read from `chunk_count`.

        Paginating a listing needs the size of the real result set, which after a failed and
        re-run materialisation is the row count and not the denormalised counter.
        """
        stmt = (
            select(func.count())
            .select_from(Chunk)
            .where(Chunk.chunk_result_id == chunk_result_id)
        )
        return await self.session.scalar(stmt) or 0
