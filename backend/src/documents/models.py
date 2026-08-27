from __future__ import annotations

from typing import Any

from sqlalchemy import BigInteger, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from src.infrastructure.database.enums import DOCUMENT_STATUS, DocumentStatus


class Document(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A file identified by its content hash; immutable and parse-independent.

    `status` tracks the acquisition of the file (fetch, hash, upload), which is a
    property of the file itself and not of its membership in a corpus. Parsing and
    chunking state lives on the pipeline artefacts, because it exists per
    configuration.
    """

    __tablename__ = "documents"

    content_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        DOCUMENT_STATUS,
        nullable=False,
        server_default=DocumentStatus.PENDING.value,
    )
    error: Mapped[str | None] = mapped_column(Text)
    document_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}", default=dict
    )
