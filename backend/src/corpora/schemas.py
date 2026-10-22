from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field


class CorpusRead(BaseModel):
    """A corpus as exposed by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None = None
    created_at: dt.datetime
    updated_at: dt.datetime


class CorpusCreate(BaseModel):
    """Payload creating a corpus."""

    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class CorpusUpdate(BaseModel):
    """Payload updating a corpus; omitted fields are left unchanged."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class CorpusDocumentsAdd(BaseModel):
    """Payload adding existing documents to a corpus."""

    document_ids: list[uuid.UUID] = Field(min_length=1)


class CorpusDocumentsAdded(BaseModel):
    """Result of adding documents to a corpus."""

    corpus_id: uuid.UUID
    document_count: int


class CorpusDocumentRemoved(BaseModel):
    """Result of detaching a document from a corpus.

    States explicitly that the snapshots survive, because "remove" is the one word a user
    could read as "delete the file and everything measured on it".
    """

    corpus_id: uuid.UUID
    document_id: uuid.UUID
    snapshots_unaffected: bool = True
    detail: str = (
        "the document was removed from the corpus; it still exists and existing "
        "snapshots keep their frozen composition"
    )


class CorpusProgress(BaseModel):
    """Acquisition progress of a corpus, one count per document status."""

    corpus_id: uuid.UUID
    total: int
    by_status: dict[str, int] = Field(default_factory=dict)


class CorpusSnapshotRead(BaseModel):
    """A frozen selection of documents as exposed by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    corpus_id: uuid.UUID
    label: str
    document_count: int
    composition_hash: str
    frozen_at: dt.datetime


class CorpusSnapshotCreate(BaseModel):
    """Payload freezing a snapshot; without `document_ids` every stored document is taken."""

    label: str = Field(min_length=1, max_length=200)
    document_ids: list[uuid.UUID] | None = Field(default=None, min_length=1)


class CorpusSnapshotCreated(BaseModel):
    """A snapshot with the outcome of the get-or-create that returned it."""

    snapshot: CorpusSnapshotRead
    created: bool
    detail: str | None = None
