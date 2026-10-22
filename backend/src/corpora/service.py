from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.get_or_create import get_or_create_reporting
from src.core.hashing import composition_hash
from src.corpora.exceptions import (
    CorpusHasSnapshotsError,
    CorpusNotFoundError,
    CorpusSnapshotNotFoundError,
    DocumentsNotInCorpusError,
    EmptySnapshotError,
    UnknownDocumentsError,
)
from src.corpora.models import Corpus, CorpusSnapshot
from src.corpora.repository import (
    CorpusDocumentRepository,
    CorpusRepository,
    CorpusSnapshotRepository,
)
from src.documents.models import Document
from src.documents.repository import DocumentRepository
from src.infrastructure.database.enums import DocumentStatus


class CorpusService:
    """Lifecycle of a corpus and of its current membership.

    Membership is mutable while snapshots are not: this class only ever touches
    `corpus_documents`, so removing a document changes what the *next* snapshot will
    contain and leaves every existing one intact.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.corpora = CorpusRepository(session)
        self.memberships = CorpusDocumentRepository(session)
        self.snapshots = CorpusSnapshotRepository(session)
        self.documents = DocumentRepository(session)

    async def create(self, name: str, description: str | None = None) -> Corpus:
        """Create a corpus.

        Not a get-or-create on the name: two corpora may legitimately share a label while
        differing in composition, and the name is not part of the identity of anything.
        """
        corpus = self.corpora.add(Corpus(name=name, description=description))
        await self.session.flush()
        return corpus

    async def get(self, corpus_id: uuid.UUID) -> Corpus:
        """Return a corpus by id.

        Raises:
            CorpusNotFoundError: If it does not exist.
        """
        corpus = await self.corpora.get_by_id(corpus_id)
        if corpus is None:
            raise CorpusNotFoundError(corpus_id)
        return corpus

    async def list(
        self, *, limit: int = 50, offset: int = 0
    ) -> tuple[Sequence[Corpus], int]:
        """List the corpora with the total count."""
        items = await self.corpora.list(limit=limit, offset=offset)
        return items, await self.corpora.count()

    async def update(
        self,
        corpus_id: uuid.UUID,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> Corpus:
        """Update the label of a corpus; `None` means "leave unchanged".

        Raises:
            CorpusNotFoundError: If the corpus does not exist.
        """
        corpus = await self.get(corpus_id)
        if name is not None:
            corpus.name = name
        if description is not None:
            corpus.description = description
        await self.session.flush()
        # `updated_at` is computed by the database via `onupdate`, so the flush leaves the
        # attribute expired; without the refresh reading it back would need lazy IO.
        await self.session.refresh(corpus)
        return corpus

    async def delete(self, corpus_id: uuid.UUID) -> None:
        """Delete a corpus that was never frozen.

        Raises:
            CorpusNotFoundError: If the corpus does not exist.
            CorpusHasSnapshotsError: If snapshots exist, because deleting the corpus would
                cascade them away and with them the meaning of past measurements.
        """
        corpus = await self.get(corpus_id)
        snapshots = await self.snapshots.list_by_corpus(corpus_id, limit=1)
        if snapshots:
            raise CorpusHasSnapshotsError(corpus_id, len(snapshots))
        await self.corpora.delete(corpus)
        await self.session.flush()

    async def add_documents(
        self, corpus_id: uuid.UUID, document_ids: Sequence[uuid.UUID]
    ) -> int:
        """Add existing documents to a corpus, ignoring the ones already in it.

        Args:
            corpus_id: Corpus to file the documents into.
            document_ids: Documents to add; duplicates and order are irrelevant.

        Returns:
            The number of documents in the corpus after the operation.

        Raises:
            CorpusNotFoundError: If the corpus does not exist.
            UnknownDocumentsError: If an id matches no document, so a typo is rejected
                instead of silently adding nothing.
        """
        await self.get(corpus_id)
        unique_ids = list(dict.fromkeys(document_ids))
        if unique_ids:
            await self._assert_documents_exist(unique_ids)
            await self.memberships.add_documents(corpus_id, unique_ids)
        return await self.memberships.count(corpus_id)

    async def remove_document(
        self, corpus_id: uuid.UUID, document_id: uuid.UUID
    ) -> None:
        """Detach a document from a corpus.

        The document itself and every snapshot that froze it are untouched: this is a
        "remove from corpus", not a "delete document".

        Raises:
            CorpusNotFoundError: If the corpus does not exist.
        """
        await self.get(corpus_id)
        await self.memberships.remove_document(corpus_id, document_id)
        await self.session.flush()

    async def list_documents(
        self,
        corpus_id: uuid.UUID,
        *,
        status: DocumentStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[Sequence[Document], int]:
        """List the documents of a corpus with the total count.

        Raises:
            CorpusNotFoundError: If the corpus does not exist, so an unknown id is a 404
                and not an empty corpus.
        """
        await self.get(corpus_id)
        rows = await self.memberships.list_documents(
            corpus_id, status=status, limit=limit, offset=offset
        )
        total = await self.memberships.count(corpus_id, status=status)
        return [document for _, document in rows], total

    async def progress(self, corpus_id: uuid.UUID) -> dict[str, int]:
        """Acquisition progress of a corpus, as a count per document status.

        Every status is present, zero included, so the UI renders a stable set of bars
        instead of one that appears and disappears with the data.

        Raises:
            CorpusNotFoundError: If the corpus does not exist.
        """
        await self.get(corpus_id)
        counts = await self.memberships.count_by_status(corpus_id)
        return {status.value: counts.get(status, 0) for status in DocumentStatus}

    async def _assert_documents_exist(self, document_ids: Sequence[uuid.UUID]) -> None:
        """Check that every id refers to an existing document."""
        found = {
            document.id for document in await self.documents.list_by_ids(document_ids)
        }
        missing = [str(doc_id) for doc_id in document_ids if doc_id not in found]
        if missing:
            raise UnknownDocumentsError(missing)


class CorpusSnapshotService:
    """Freezing of a corpus selection into an immutable snapshot."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.corpora = CorpusRepository(session)
        self.snapshots = CorpusSnapshotRepository(session)
        self.memberships = CorpusDocumentRepository(session)

    async def get_or_create(
        self,
        corpus_id: uuid.UUID,
        document_ids: Sequence[uuid.UUID],
        *,
        label: str,
    ) -> CorpusSnapshot:
        """Freeze a selection of documents, reusing the snapshot with the same composition.

        See `get_or_create_reporting`, which this wraps for callers that do not need to
        know whether the snapshot was new.
        """
        snapshot, _created = await self.get_or_create_reporting(
            corpus_id, document_ids, label=label
        )
        return snapshot

    async def get_or_create_reporting(
        self,
        corpus_id: uuid.UUID,
        document_ids: Sequence[uuid.UUID] | None,
        *,
        label: str,
    ) -> tuple[CorpusSnapshot, bool]:
        """Freeze a selection of documents and report whether this call created it.

        Deduplication is mandatory: the snapshot is part of the meaning of a
        metric, so two snapshots with the same composition would split one experiment
        into two non-comparable groups. Creation is therefore always a get-or-create on
        `(corpus_id, composition_hash)`.

        Args:
            corpus_id: Corpus the selection is taken from.
            document_ids: Documents to freeze; duplicates and order are irrelevant. `None`
                freezes every stored document of the corpus, i.e. the ones that can be
                parsed: pending or failed acquisitions would only fail the index build.
            label: Human-readable label, used only when a new snapshot is created.

        Returns:
            The snapshot with this composition and whether this call created it.

        Raises:
            CorpusNotFoundError: If the corpus does not exist.
            EmptySnapshotError: If no document is selected.
            DocumentsNotInCorpusError: If a document does not belong to the corpus.
        """
        if await self.corpora.get_by_id(corpus_id) is None:
            raise CorpusNotFoundError(corpus_id)
        if document_ids is None:
            document_ids = await self.memberships.list_document_ids(
                corpus_id, status=DocumentStatus.STORED
            )

        unique_ids = sorted(set(document_ids), key=str)
        if not unique_ids:
            raise EmptySnapshotError

        await self._assert_membership(corpus_id, unique_ids)

        digest = composition_hash(unique_ids)

        async def create() -> CorpusSnapshot:
            snapshot = self.snapshots.add(
                CorpusSnapshot(
                    corpus_id=corpus_id,
                    label=label,
                    document_count=len(unique_ids),
                    composition_hash=digest,
                )
            )
            await self.session.flush()
            await self.snapshots.add_snapshot_documents(snapshot.id, unique_ids)
            return snapshot

        return await get_or_create_reporting(
            self.session,
            lookup=lambda: self.snapshots.get_by_composition(corpus_id, digest),
            create=create,
        )

    async def get(self, corpus_id: uuid.UUID, snapshot_id: uuid.UUID) -> CorpusSnapshot:
        """Return a snapshot of a corpus.

        Raises:
            CorpusSnapshotNotFoundError: If it does not exist or belongs to another corpus.
        """
        snapshot = await self.snapshots.get_by_id(snapshot_id)
        if snapshot is None or snapshot.corpus_id != corpus_id:
            raise CorpusSnapshotNotFoundError(snapshot_id)
        return snapshot

    async def list(
        self, corpus_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> tuple[Sequence[CorpusSnapshot], int]:
        """One page of a corpus' snapshots, newest first, and the size of the whole set.

        Raises:
            CorpusNotFoundError: If the corpus does not exist.
        """
        if await self.corpora.get_by_id(corpus_id) is None:
            raise CorpusNotFoundError(corpus_id)
        snapshots = await self.snapshots.list_by_corpus(
            corpus_id, limit=limit, offset=offset
        )
        return snapshots, await self.snapshots.count_by_corpus(corpus_id)

    async def list_documents(
        self,
        corpus_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[Sequence[Document], int]:
        """One page of the documents frozen into a snapshot and their total.

        Raises:
            CorpusSnapshotNotFoundError: If the snapshot does not belong to the corpus.
        """
        await self.get(corpus_id, snapshot_id)
        documents = await self.snapshots.list_snapshot_documents(
            snapshot_id, limit=limit, offset=offset
        )
        return documents, await self.snapshots.count_snapshot_documents(snapshot_id)

    async def _assert_membership(
        self, corpus_id: uuid.UUID, document_ids: Sequence[uuid.UUID]
    ) -> None:
        """Check that the selection is a subset of the current corpus."""
        in_corpus = set(await self.memberships.list_document_ids(corpus_id))
        missing = [str(doc_id) for doc_id in document_ids if doc_id not in in_corpus]
        if missing:
            raise DocumentsNotInCorpusError(missing)
