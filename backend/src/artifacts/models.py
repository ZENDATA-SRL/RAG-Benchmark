from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from src.infrastructure.database.enums import ARTIFACT_STATUS, ArtifactStatus


class ParsingResult(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Output of a parser on a **single** document; cache key: document + parsing profile.

    `output_uri` is nullable, unlike what the data model would suggest: the row is inserted
    when the artefact is claimed (`pending`) so that the cache key acts as the lock, and
    the storage reference only exists once the parse succeeded. The CHECK constraint
    keeps the guarantee where it matters, i.e. a `ready` parse always has an output.
    """

    __tablename__ = "parsing_results"
    __table_args__ = (
        UniqueConstraint("document_id", "parsing_profile_id"),
        # Support for the composite FK of `chunk_results`.
        UniqueConstraint("id", "parsing_profile_id"),
        CheckConstraint(
            "status <> 'ready' OR output_uri IS NOT NULL",
            name="output_uri_required_when_ready",
        ),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    parsing_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("parsing_profiles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    output_uri: Mapped[str | None] = mapped_column(Text)
    output_text: Mapped[str | None] = mapped_column(Text)
    cache_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    status: Mapped[ArtifactStatus] = mapped_column(
        ARTIFACT_STATUS, nullable=False, server_default=ArtifactStatus.PENDING.value
    )
    error: Mapped[str | None] = mapped_column(Text)


class ChunkResult(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Output of a chunker on a **single** document, from a parse of the same document.

    Cache key: document + chunking configuration. The two composite foreign keys
    guarantee declaratively that the input parse belongs to the parsing profile declared
    by the configuration; `parsing_profile_id` is the redundant column they share. It
    costs two supporting unique indexes and removes an application check that would
    eventually be forgotten.

    The scope assumption is document-local: a chunker that deduplicates
    boilerplate across the whole corpus is not cacheable per document, and in v1 only
    `document` scoped chunkers are admitted via `capabilities.scope`.
    """

    __tablename__ = "chunk_results"
    __table_args__ = (
        UniqueConstraint("document_id", "chunking_configuration_id"),
        # The composite FKs subsume the single-column ones on `parsing_result_id` and
        # `chunking_configuration_id`, so those are not declared twice.
        ForeignKeyConstraint(
            ["parsing_result_id", "parsing_profile_id"],
            ["parsing_results.id", "parsing_results.parsing_profile_id"],
            ondelete="RESTRICT",
            name="fk_chunk_results_parse_parsing_profile",
        ),
        ForeignKeyConstraint(
            ["chunking_configuration_id", "parsing_profile_id"],
            [
                "chunking_configurations.id",
                "chunking_configurations.parsing_profile_id",
            ],
            ondelete="RESTRICT",
            name="fk_chunk_results_configuration_parsing_profile",
        ),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunking_configuration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    parsing_result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    parsing_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    cache_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    chunk_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), default=0
    )
    status: Mapped[ArtifactStatus] = mapped_column(
        ARTIFACT_STATUS, nullable=False, server_default=ArtifactStatus.PENDING.value
    )
    error: Mapped[str | None] = mapped_column(Text)

    chunks: Mapped[list[Chunk]] = relationship(
        back_populates="chunk_result", cascade="all, delete-orphan"
    )


class Chunk(UUIDPrimaryKeyMixin, Base):
    """Indexable unit: text, modality and metadata; the vectors live in the vector store.

    Document and chunking configuration are implied by `chunk_result_id`, and the
    identity of the row depends only on that plus `ordinal`.
    """

    __tablename__ = "chunks"
    __table_args__ = (UniqueConstraint("chunk_result_id", "ordinal"),)

    chunk_result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chunk_results.id", ondelete="CASCADE"),
        nullable=False,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    modality: Mapped[str] = mapped_column(Text, nullable=False, server_default="text")
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}", default=dict
    )
    text_normalized: Mapped[str | None] = mapped_column(Text)

    chunk_result: Mapped[ChunkResult] = relationship(back_populates="chunks")
