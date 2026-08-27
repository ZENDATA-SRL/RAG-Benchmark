from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.corpora.models import (
    Corpus,
    CorpusDocument,
    CorpusSnapshot,
    CorpusSnapshotDocument,
)
from src.documents.models import Document
from src.infrastructure.database.enums import DocumentStatus


class CorpusRepository:
    """Data access for `corpora`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, corpus: Corpus) -> Corpus:
        self.session.add(corpus)
        return corpus

    async def get_by_id(self, corpus_id: uuid.UUID) -> Corpus | None:
        return await self.session.get(Corpus, corpus_id)

    async def list(self, *, limit: int = 50, offset: int = 0) -> Sequence[Corpus]:
        stmt = select(Corpus).order_by(Corpus.name).limit(limit).offset(offset)
        result = await self.session.scalars(stmt)
        return result.all()

    async def delete(self, corpus: Corpus) -> None:
        await self.session.delete(corpus)


class CorpusDocumentRepository:
    """Data access for `corpus_documents` (current corpus membership)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_documents(
        self, corpus_id: uuid.UUID, document_ids: Sequence[uuid.UUID]
    ) -> None:
        """Attach documents to a corpus, ignoring documents already present."""
        if not document_ids:
            return
        stmt = (
            pg_insert(CorpusDocument)
            .values([{"corpus_id": corpus_id, "document_id": doc_id} for doc_id in document_ids])
            .on_conflict_do_nothing(index_elements=["corpus_id", "document_id"])
        )
        await self.session.execute(stmt)

    async def get(self, corpus_id: uuid.UUID, document_id: uuid.UUID) -> CorpusDocument | None:
        return await self.session.get(CorpusDocument, (corpus_id, document_id))

    async def remove_document(self, corpus_id: uuid.UUID, document_id: uuid.UUID) -> None:
        """Detach a document from the corpus; existing snapshots stay valid."""
        membership = await self.get(corpus_id, document_id)
        if membership is not None:
            await self.session.delete(membership)

    async def list_documents(
        self,
        corpus_id: uuid.UUID,
        *,
        status: DocumentStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[tuple[CorpusDocument, Document]]:
        """List corpus membership rows joined with their document."""
        stmt = (
            select(CorpusDocument, Document)
            .join(Document, Document.id == CorpusDocument.document_id)
            .where(CorpusDocument.corpus_id == corpus_id)
        )
        if status is not None:
            stmt = stmt.where(Document.status == status)
        stmt = stmt.order_by(CorpusDocument.added_at, Document.filename).limit(limit).offset(offset)
        rows = await self.session.execute(stmt)
        return [(membership, document) for membership, document in rows.all()]

    async def list_document_ids(self, corpus_id: uuid.UUID) -> Sequence[uuid.UUID]:
        stmt = select(CorpusDocument.document_id).where(CorpusDocument.corpus_id == corpus_id)
        result = await self.session.scalars(stmt)
        return result.all()

    async def count(self, corpus_id: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(CorpusDocument).where(
            CorpusDocument.corpus_id == corpus_id
        )
        return await self.session.scalar(stmt) or 0

    async def count_by_status(self, corpus_id: uuid.UUID) -> dict[DocumentStatus, int]:
        """Acquisition progress of a corpus (RF-C04), aggregated over its memberships.

        The status lives on `documents`, so the progress of a corpus is an aggregate
        over the join and not a stored column.
        """
        stmt = (
            select(Document.status, func.count())
            .join(CorpusDocument, CorpusDocument.document_id == Document.id)
            .where(CorpusDocument.corpus_id == corpus_id)
            .group_by(Document.status)
        )
        rows = await self.session.execute(stmt)
        return {status: count for status, count in rows.all()}


class CorpusSnapshotRepository:
    """Data access for `corpus_snapshots` and their immutable composition."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, snapshot: CorpusSnapshot) -> CorpusSnapshot:
        self.session.add(snapshot)
        return snapshot

    async def get_by_id(self, snapshot_id: uuid.UUID) -> CorpusSnapshot | None:
        return await self.session.get(CorpusSnapshot, snapshot_id)

    async def get_by_composition(
        self, corpus_id: uuid.UUID, composition_hash: str
    ) -> CorpusSnapshot | None:
        """Look up an existing snapshot by its dedup key (RF-C07)."""
        stmt = select(CorpusSnapshot).where(
            CorpusSnapshot.corpus_id == corpus_id,
            CorpusSnapshot.composition_hash == composition_hash,
        )
        return await self.session.scalar(stmt)

    async def list_by_corpus(
        self, corpus_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> Sequence[CorpusSnapshot]:
        stmt = (
            select(CorpusSnapshot)
            .where(CorpusSnapshot.corpus_id == corpus_id)
            .order_by(CorpusSnapshot.frozen_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.scalars(stmt)
        return result.all()

    async def add_snapshot_documents(
        self, snapshot_id: uuid.UUID, document_ids: Sequence[uuid.UUID]
    ) -> None:
        """Write the frozen composition of a snapshot (called once, at freeze time)."""
        if not document_ids:
            return
        stmt = pg_insert(CorpusSnapshotDocument).values(
            [{"snapshot_id": snapshot_id, "document_id": doc_id} for doc_id in document_ids]
        )
        await self.session.execute(stmt)

    async def list_snapshot_documents(
        self, snapshot_id: uuid.UUID, *, limit: int = 100, offset: int = 0
    ) -> Sequence[Document]:
        """List the documents frozen into a snapshot."""
        stmt = (
            select(Document)
            .join(CorpusSnapshotDocument, CorpusSnapshotDocument.document_id == Document.id)
            .where(CorpusSnapshotDocument.snapshot_id == snapshot_id)
            .order_by(Document.filename, Document.id)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.scalars(stmt)
        return result.all()

    async def count_snapshot_documents(self, snapshot_id: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(CorpusSnapshotDocument).where(
            CorpusSnapshotDocument.snapshot_id == snapshot_id
        )
        return await self.session.scalar(stmt) or 0
