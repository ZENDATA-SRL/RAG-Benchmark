from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.infrastructure.database.enums import DocumentStatus, FileOutcome
from src.sources.schemas import DocumentProvenanceRead


class DocumentRead(BaseModel):
    """A document as exposed by the API.

    `content_hash` is always exposed: it is the identity the platform deduplicates on, so
    it is also the only way a user can tell that the file they just uploaded is the one
    already in the list.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    content_hash: str
    filename: str
    mime_type: str
    size_bytes: int
    storage_uri: str
    status: DocumentStatus
    error: str | None = None
    metadata: dict[str, Any] = Field(
        default_factory=dict, validation_alias="document_metadata"
    )
    created_at: dt.datetime


class DocumentWithProvenancesRead(DocumentRead):
    """A document together with its origins, so the UI resolves the original."""

    provenances: list[DocumentProvenanceRead] = Field(default_factory=list)


class DocumentMetadataUpdate(BaseModel):
    """Payload replacing the metadata of a document.

    The shape is free because the keys become retrieval filters and are not known to the
    platform; it is a filter surface and not a notes field.
    """

    metadata: dict[str, Any] = Field(default_factory=dict)


class UploadFileResult(BaseModel):
    """Outcome of one file of an upload request."""

    filename: str
    outcome: FileOutcome
    document_id: uuid.UUID | None = None
    error_reason: str | None = None


class UploadResponse(BaseModel):
    """Summary of an upload request, one entry per submitted file.

    Returned with `200` even when some files were rejected: the outcome is per file, and a
    single unsupported attachment must not discard the batch.
    """

    import_run_id: uuid.UUID
    results: list[UploadFileResult] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
