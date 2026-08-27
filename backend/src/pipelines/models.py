from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Double,
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

# --------------------------------------------------------------------------------------
# Profiles
# --------------------------------------------------------------------------------------


class ParsingProfile(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Reusable parsing configuration: component version + parameters (RF-P01)."""

    __tablename__ = "parsing_profiles"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    component_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("component_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    params: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}", default=dict
    )
    config_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)


class ChunkingProfile(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Reusable chunking configuration (RF-P02).

    `params` carries the header/footer/index filter policy (RF-P03) and the image
    policy; both are per-document, so neither makes the chunker corpus-scoped.
    """

    __tablename__ = "chunking_profiles"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    component_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("component_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    strategy: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_size: Mapped[int | None] = mapped_column(Integer)
    overlap: Mapped[int | None] = mapped_column(Integer)
    params: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}", default=dict
    )
    config_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)


class EmbeddingProfile(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Embedding configuration, with text, image and multi-vector support (RF-P04)."""

    __tablename__ = "embedding_profiles"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    component_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("component_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    modality: Mapped[str] = mapped_column(Text, nullable=False, server_default="text")
    dimensions: Mapped[int | None] = mapped_column(Integer)
    params: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}", default=dict
    )
    config_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)


class VectorStoreProfile(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Vector store configuration with its index parameters (RF-P05)."""

    __tablename__ = "vector_store_profiles"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    component_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("component_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    index_params: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}", default=dict
    )
    config_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)


class RetrievalProfile(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Full retrieval configuration (RF-P06).

    Referenced by variants and never materialised as a stage: changing `top_k` or the
    reranker invalidates no parsing, chunking or index artefact.
    """

    __tablename__ = "retrieval_profiles"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    pre_rerank_k: Mapped[int | None] = mapped_column(Integer)
    strategy: Mapped[str] = mapped_column(Text, nullable=False)
    fusion_weights: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    mmr: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    score_threshold: Mapped[float | None] = mapped_column(Double)
    metadata_filters: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    query_transforms: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    reranker_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("component_versions.id", ondelete="RESTRICT"),
        index=True,
    )
    context_policy: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    config_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)


# --------------------------------------------------------------------------------------
# Artefacts
# --------------------------------------------------------------------------------------


class ParsingResult(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Output of a parser on a **single** document; cache key: document + parsing profile.

    `output_uri` is nullable, unlike the table in `DATA_MODEL.md`: the row is inserted
    when the artefact is claimed (`pending`) so that the cache key acts as the lock, and
    the storage reference only exists once the parse succeeded. The CHECK constraint
    keeps the doc's guarantee where it matters, i.e. a `ready` parse always has an output.
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
    cache_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    status: Mapped[ArtifactStatus] = mapped_column(
        ARTIFACT_STATUS, nullable=False, server_default=ArtifactStatus.PENDING.value
    )
    error: Mapped[str | None] = mapped_column(Text)


class ChunkingConfiguration(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """The (parsing profile, chunking profile) pair, materialised as an entity (§3.1).

    This is the comparability dimension of chunk-level gold and the only dimension whose
    change costs human work, which is why `evidence_links` point here and not at an
    index build: a confirmed link stays valid when the embedder, the vector store, the
    top-k or the snapshot composition change.
    """

    __tablename__ = "chunking_configurations"
    __table_args__ = (
        UniqueConstraint(
            "parsing_profile_id",
            "chunking_profile_id",
            name="uq_chunking_configurations_profiles",
        ),
        # Support for the composite FK of `chunk_results`.
        UniqueConstraint("id", "parsing_profile_id"),
    )

    name: Mapped[str] = mapped_column(Text, nullable=False)
    parsing_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("parsing_profiles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    chunking_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chunking_profiles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    config_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)


class ChunkResult(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Output of a chunker on a **single** document, from a parse of the same document.

    Cache key: document + chunking configuration. The two composite foreign keys
    guarantee declaratively that the input parse belongs to the parsing profile declared
    by the configuration; `parsing_profile_id` is the redundant column they share. It
    costs two supporting unique indexes and removes an application check that would
    eventually be forgotten.

    The scope assumption is document-local (RF-P10): a chunker that deduplicates
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


class IndexBuild(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """The vector DB population configuration (RF-P09).

    Snapshot x chunking configuration x embedder x vector store, identified by a
    fingerprint of the whole chain. The snapshot enters here because the search space is
    a property of the index and not of the experiment: `chain_fingerprint` then really
    identifies everything the content of the index depends on, and an experiment becomes
    a choice among already built indexes.

    The set of chunks of an index is not materialised: it is the query over
    `chunks -> chunk_results` filtered by `chunking_configuration_id` and by the
    documents in `corpus_snapshot_documents`.
    """

    __tablename__ = "index_builds"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    corpus_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("corpus_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    chunking_configuration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chunking_configurations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    embedding_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("embedding_profiles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    vector_store_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vector_store_profiles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    chain_fingerprint: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    external_index_ref: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ArtifactStatus] = mapped_column(
        ARTIFACT_STATUS, nullable=False, server_default=ArtifactStatus.PENDING.value
    )
    workflow_id: Mapped[str | None] = mapped_column(Text, unique=True)
