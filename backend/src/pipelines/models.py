from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Double, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from src.infrastructure.database.enums import RETRIEVAL_STRATEGY, RetrievalStrategy

# --------------------------------------------------------------------------------------
# Profiles
# --------------------------------------------------------------------------------------


class ParsingProfile(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Reusable parsing configuration: component version + parameters."""

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
    """Reusable chunking configuration.

    `params` carries the header/footer/index filter policy and the image
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
    """Embedding configuration, with text, image and multi-vector support."""

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
    """Vector store configuration with its index parameters."""

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
    """Full retrieval configuration: how the vector store of an index is searched.

    Referenced by variants and never materialised as a stage: changing `top_k` or the
    reranker invalidates no parsing, chunking or index artefact. Rewriting the query
    (HyDE, multi-query) is not part of it: that is a choice of the answer system, which
    decides what to send to the retrieval tool.
    """

    __tablename__ = "retrieval_profiles"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    pre_rerank_k: Mapped[int | None] = mapped_column(Integer)
    strategy: Mapped[RetrievalStrategy] = mapped_column(
        RETRIEVAL_STRATEGY, nullable=False
    )
    fusion_weights: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    mmr: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    score_threshold: Mapped[float | None] = mapped_column(Double)
    metadata_filters: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    reranker_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("component_versions.id", ondelete="RESTRICT"),
        index=True,
    )
    context_policy: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    config_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)


# --------------------------------------------------------------------------------------
# Chunking configurations
# --------------------------------------------------------------------------------------


class ChunkingConfiguration(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """The (parsing profile, chunking profile) pair, materialised as an entity.

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
