from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.artifacts.models import Chunk, ChunkResult
from src.components.models import Component, ComponentVersion
from src.corpora.models import CorpusSnapshot
from src.documents.models import Document


class RetrievalRepository:
    """The database reads a query needs around the vector store call."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def component_key(self, component_version_id: uuid.UUID) -> str | None:
        """Key of the component a version belongs to, e.g. `openai` or `qdrant`."""
        stmt = (
            select(Component.key)
            .join(ComponentVersion, ComponentVersion.component_id == Component.id)
            .where(ComponentVersion.id == component_version_id)
        )
        return await self.session.scalar(stmt)

    async def snapshot_corpus_id(self, snapshot_id: uuid.UUID) -> uuid.UUID | None:
        """Corpus a snapshot was frozen from."""
        stmt = select(CorpusSnapshot.corpus_id).where(CorpusSnapshot.id == snapshot_id)
        return await self.session.scalar(stmt)

    async def chunks_by_id(
        self, chunk_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, tuple[Chunk, uuid.UUID, str]]:
        """Chunks with their document id and filename, keyed by chunk id.

        Ids that no longer exist in the database are simply absent from the result.
        """
        if not chunk_ids:
            return {}
        stmt = (
            select(Chunk, ChunkResult.document_id, Document.filename)
            .join(ChunkResult, ChunkResult.id == Chunk.chunk_result_id)
            .join(Document, Document.id == ChunkResult.document_id)
            .where(Chunk.id.in_(chunk_ids))
        )
        rows = await self.session.execute(stmt)
        return {
            chunk.id: (chunk, document_id, filename)
            for chunk, document_id, filename in rows.all()
        }
