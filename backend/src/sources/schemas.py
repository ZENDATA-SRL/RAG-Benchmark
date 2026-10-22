from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict

from src.infrastructure.database.enums import (
    AuthMethod,
    FileOutcome,
    ImportStatus,
    SourceType,
)


class SourceConnectionRead(BaseModel):
    """A source connection as exposed by the API; never carries a secret."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    type: SourceType
    endpoint: str | None = None
    root_path: str | None = None
    auth_method: AuthMethod
    created_at: dt.datetime


class DocumentProvenanceRead(BaseModel):
    """Where one copy of a document came from."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    connection_id: uuid.UUID
    original_uri: str
    native_id: str | None = None
    source_modified_at: dt.datetime | None = None
    created_at: dt.datetime


class ImportFileResultRead(BaseModel):
    """Outcome of a single file inside an import run."""

    model_config = ConfigDict(from_attributes=True)

    source_uri: str
    outcome: FileOutcome
    document_id: uuid.UUID | None = None
    error_reason: str | None = None


class ImportRunRead(BaseModel):
    """Summary of an import run."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    selection_id: uuid.UUID
    status: ImportStatus
    counts: dict[str, Any]
    started_at: dt.datetime | None = None
    finished_at: dt.datetime | None = None
    created_at: dt.datetime
