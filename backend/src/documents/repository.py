from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.documents.models import Document
from src.infrastructure.database.enums import DocumentStatus


class DocumentRepository:
    """Data access for `documents`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, document: Document) -> Document:
        """Stage a new document for insertion."""
        self.session.add(document)
        return document

    async def get_by_id(self, document_id: uuid.UUID) -> Document | None:
        return await self.session.get(Document, document_id)

    async def get_by_content_hash(self, content_hash: str) -> Document | None:
        """Look up a document by its dedup key."""
        stmt = select(Document).where(Document.content_hash == content_hash)
        return await self.session.scalar(stmt)

    async def list_by_status(
        self, status: DocumentStatus, *, limit: int = 100, offset: int = 0
    ) -> Sequence[Document]:
        """List documents by acquisition status, e.g. to resume failed fetches."""
        stmt = (
            select(Document)
            .where(Document.status == status)
            .order_by(Document.created_at, Document.id)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.scalars(stmt)
        return result.all()

    async def list_by_content_hashes(self, content_hashes: Sequence[str]) -> Sequence[Document]:
        """Batch lookup used to detect duplicates during an import run."""
        if not content_hashes:
            return []
        stmt = select(Document).where(Document.content_hash.in_(content_hashes))
        result = await self.session.scalars(stmt)
        return result.all()

    async def list_by_ids(self, document_ids: Sequence[uuid.UUID]) -> Sequence[Document]:
        if not document_ids:
            return []
        stmt = select(Document).where(Document.id.in_(document_ids))
        result = await self.session.scalars(stmt)
        return result.all()

    async def list(
        self, *, status: DocumentStatus | None = None, limit: int = 50, offset: int = 0
    ) -> Sequence[Document]:
        stmt = select(Document)
        if status is not None:
            stmt = stmt.where(Document.status == status)
        stmt = (
            stmt.order_by(Document.created_at.desc(), Document.id).limit(limit).offset(offset)
        )
        result = await self.session.scalars(stmt)
        return result.all()

    async def count(self, *, status: DocumentStatus | None = None) -> int:
        """Total number of documents matching the filter, for the `total` of a page."""
        stmt = select(func.count()).select_from(Document)
        if status is not None:
            stmt = stmt.where(Document.status == status)
        return await self.session.scalar(stmt) or 0
