from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field

from src.infrastructure.database.enums import ArtifactStatus


class MaterializationCreate(BaseModel):
    """Payload launching a materialisation.

    Either an explicit document list — the preview on a few files (RF-P08) — or a corpus,
    whose documents are resolved server-side. The same endpoint and the same workflow serve
    both, so a preview is exactly what the full run will do.
    """

    chunking_configuration_id: uuid.UUID
    document_ids: list[uuid.UUID] | None = Field(default=None, min_length=1)
    corpus_id: uuid.UUID | None = None
    concurrency: int | None = Field(default=None, ge=1, le=50)


class MaterializationProgress(BaseModel):
    """The four counters of a run; they always sum to `document_count`."""

    ready: int = 0
    failed: int = 0
    cached: int = 0
    pending: int = 0


class DocumentFailureRead(BaseModel):
    """Why one document of a run produced no chunks."""

    document_id: uuid.UUID
    error: str | None = None


class MaterializationRead(BaseModel):
    """A materialisation run as exposed by the API.

    Denormalised on purpose (RT-O07): the UI polls this every couple of seconds and must not
    make Temporal answer each refresh. The authoritative state stays in Temporal.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chunking_configuration_id: uuid.UUID
    corpus_id: uuid.UUID | None = None
    workflow_id: str
    status: ArtifactStatus
    document_count: int
    progress: MaterializationProgress = Field(default_factory=MaterializationProgress)
    error: str | None = None
    started_at: dt.datetime | None = None
    finished_at: dt.datetime | None = None
    created_at: dt.datetime


class MaterializationDetail(MaterializationRead):
    """A run with the reason of each document that failed."""

    failures: list[DocumentFailureRead] = Field(default_factory=list)


class MaterializationAccepted(MaterializationRead):
    """A launched run, stating whether this request is what started it.

    `started` is false when the deterministic workflow id was already running: two identical
    launches produce one workflow and two `202`s with the same `id`, because a double click is
    not a user error (RT-O01).
    """

    started: bool
    detail: str | None = None
