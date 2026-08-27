from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.base import (
    Base,
    CreatedAtMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from src.infrastructure.database.enums import (
    AUTH_METHOD,
    FILE_OUTCOME,
    IMPORT_STATUS,
    SOURCE_TYPE,
    AuthMethod,
    FileOutcome,
    ImportStatus,
    SourceType,
)


class SourceConnection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Reusable configuration towards a document system.

    Secrets are never stored: only `credential_ref` pointing at the secret store.
    """

    __tablename__ = "source_connections"
    __table_args__ = (
        CheckConstraint(
            "auth_method = 'none' OR credential_ref IS NOT NULL",
            name="credential_ref_required",
        ),
    )

    name: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[SourceType] = mapped_column(SOURCE_TYPE, nullable=False)
    endpoint: Mapped[str | None] = mapped_column(Text)
    root_path: Mapped[str | None] = mapped_column(Text)
    auth_method: Mapped[AuthMethod] = mapped_column(
        AUTH_METHOD,
        nullable=False,
        server_default=AuthMethod.NONE.value,
    )
    credential_ref: Mapped[str | None] = mapped_column(Text)
    oauth_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}", default=dict
    )
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}", default=dict
    )

    selections: Mapped[list[ImportSelection]] = relationship(
        back_populates="connection", cascade="all, delete-orphan"
    )


class ImportSelection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """What to import from a connection; the re-synchronisable unit."""

    __tablename__ = "import_selections"

    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("source_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    paths: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default="[]", default=list)
    recursive: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    filters: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}", default=dict
    )

    connection: Mapped[SourceConnection] = relationship(back_populates="selections")
    runs: Mapped[list[ImportRun]] = relationship(
        back_populates="selection", cascade="all, delete-orphan"
    )


class ImportRun(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One acquisition pass; `status`/`counts` are denormalised from Temporal."""

    __tablename__ = "import_runs"

    selection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("import_selections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workflow_id: Mapped[str | None] = mapped_column(Text, unique=True)
    status: Mapped[ImportStatus] = mapped_column(
        IMPORT_STATUS,
        nullable=False,
        server_default=ImportStatus.PENDING.value,
    )
    counts: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}", default=dict
    )
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    selection: Mapped[ImportSelection] = relationship(back_populates="runs")
    file_results: Mapped[list[ImportFileResult]] = relationship(
        back_populates="import_run", cascade="all, delete-orphan"
    )


class ImportFileResult(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Per-file outcome inside an import run."""

    __tablename__ = "import_file_results"

    import_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("import_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_uri: Mapped[str] = mapped_column(Text, nullable=False)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )
    outcome: Mapped[FileOutcome] = mapped_column(FILE_OUTCOME, nullable=False)
    error_reason: Mapped[str | None] = mapped_column(Text)

    import_run: Mapped[ImportRun] = relationship(back_populates="file_results")


class DocumentProvenance(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Many-to-many link document <-> connection: the same content may come from many sources."""

    __tablename__ = "document_provenances"
    __table_args__ = (
        UniqueConstraint("document_id", "connection_id", "original_uri"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("source_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    original_uri: Mapped[str] = mapped_column(Text, nullable=False)
    native_id: Mapped[str | None] = mapped_column(Text)
    source_modified_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
