from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.get_or_create import get_or_create
from src.core.hashing import composition_hash
from src.corpora.exceptions import DocumentsNotInCorpusError, EmptySnapshotError
from src.corpora.models import CorpusSnapshot
from src.corpora.repository import CorpusDocumentRepository, CorpusSnapshotRepository


class CorpusSnapshotService:
    """Freezing of a corpus selection into an immutable snapshot."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
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

        Deduplication is mandatory: the snapshot is part of the meaning of a
        metric, so two snapshots with the same composition would split one experiment
        into two non-comparable groups. Creation is therefore always a get-or-create on
        `(corpus_id, composition_hash)`.

        Args:
            corpus_id: Corpus the selection is taken from.
            document_ids: Documents to freeze; duplicates and order are irrelevant.
            label: Human-readable label, used only when a new snapshot is created.

        Returns:
            The existing snapshot with this composition, or the newly frozen one.

        Raises:
            EmptySnapshotError: If no document is selected.
            DocumentsNotInCorpusError: If a document does not belong to the corpus.
        """
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

        return await get_or_create(
            self.session,
            lookup=lambda: self.snapshots.get_by_composition(corpus_id, digest),
            create=create,
        )

    async def _assert_membership(
        self, corpus_id: uuid.UUID, document_ids: Sequence[uuid.UUID]
    ) -> None:
        """Check that the selection is a subset of the current corpus."""
        in_corpus = set(await self.memberships.list_document_ids(corpus_id))
        missing = [str(doc_id) for doc_id in document_ids if doc_id not in in_corpus]
        if missing:
            raise DocumentsNotInCorpusError(missing)
