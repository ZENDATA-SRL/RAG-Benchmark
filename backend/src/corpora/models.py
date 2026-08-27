from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Corpus(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Mutable logical grouping of documents, typically an organisational area."""

    __tablename__ = "corpora"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    documents: Mapped[list[CorpusDocument]] = relationship(
        back_populates="corpus", cascade="all, delete-orphan"
    )
    snapshots: Mapped[list[CorpusSnapshot]] = relationship(
        back_populates="corpus", cascade="all, delete-orphan"
    )


class CorpusDocument(Base):
    """Current membership document <-> corpus; removing a row does not affect snapshots."""

    __tablename__ = "corpus_documents"

    corpus_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("corpora.id", ondelete="CASCADE"),
        primary_key=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    added_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    corpus: Mapped[Corpus] = relationship(back_populates="documents")


class CorpusSnapshot(UUIDPrimaryKeyMixin, Base):
    """Immutable, frozen selection of documents: the search space of an index.

    Deduplicated by composition: `composition_hash` is the sha-256 over the sorted
    document ids, so selecting the same documents twice reuses the existing snapshot
    instead of creating a second, non-comparable one.
    """

    __tablename__ = "corpus_snapshots"
    __table_args__ = (UniqueConstraint("corpus_id", "composition_hash"),)

    corpus_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("corpora.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    document_count: Mapped[int] = mapped_column(Integer, nullable=False)
    composition_hash: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    frozen_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    corpus: Mapped[Corpus] = relationship(back_populates="snapshots")
    documents: Mapped[list[CorpusSnapshotDocument]] = relationship(back_populates="snapshot")


class CorpusSnapshotDocument(Base):
    """Immutable composition of a snapshot; never modified after the freeze."""

    __tablename__ = "corpus_snapshot_documents"

    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("corpus_snapshots.id", ondelete="CASCADE"),
        primary_key=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="RESTRICT"),
        primary_key=True,
    )

    snapshot: Mapped[CorpusSnapshot] = relationship(back_populates="documents")
