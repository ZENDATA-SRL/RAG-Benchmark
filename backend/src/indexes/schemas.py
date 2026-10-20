from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field

from src.infrastructure.database.enums import ArtifactStatus
from src.pipelines.schemas import DeduplicatedRead


class IndexBuildRead(BaseModel):
    """A vector DB population configuration as exposed by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    corpus_snapshot_id: uuid.UUID
    chunking_configuration_id: uuid.UUID
    embedding_profile_id: uuid.UUID
    vector_store_profile_id: uuid.UUID
    chain_fingerprint: str
    external_index_ref: str
    status: ArtifactStatus
    workflow_id: str | None = None
    created_at: dt.datetime


class IndexBuildCreate(BaseModel):
    """Payload creating an index build from an existing snapshot and profile chain."""

    corpus_snapshot_id: uuid.UUID
    chunking_configuration_id: uuid.UUID
    embedding_profile_id: uuid.UUID
    vector_store_profile_id: uuid.UUID
    name: str | None = Field(default=None, min_length=1, max_length=200)
    external_index_ref: str | None = Field(default=None, min_length=1, max_length=200)


class IndexBuildCreated(DeduplicatedRead):
    """An index build with the outcome of the get-or-create that returned it."""

    index_build: IndexBuildRead


class IndexBuildAccepted(IndexBuildRead):
    """A launched index build, stating whether this request is what started it."""

    started: bool
    detail: str | None = None
