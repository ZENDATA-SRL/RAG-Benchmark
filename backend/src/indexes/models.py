from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from src.infrastructure.database.enums import ARTIFACT_STATUS, ArtifactStatus


class IndexBuild(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """The vector DB population configuration.

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
