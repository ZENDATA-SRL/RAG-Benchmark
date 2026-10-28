from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.infrastructure.database.enums import ArtifactStatus

# --------------------------------------------------------------------------------------
# Coverage
# --------------------------------------------------------------------------------------


class ChunkingConfigurationCoverage(BaseModel):
    """How far a configuration has been materialised over a corpus.

    The three counts always sum to `total`, which is what makes the answer trustworthy: a
    document with no chunk result is `missing`, never absent.
    """

    chunking_configuration_id: uuid.UUID
    corpus_id: uuid.UUID
    total: int
    ready: int
    failed: int
    missing: int
    is_complete: bool


# --------------------------------------------------------------------------------------
# Inspection
# --------------------------------------------------------------------------------------


class ChunkRead(BaseModel):
    """A chunk as exposed by the API.

    `metadata` carries the page the chunk came from, which is what lets the UI show *where*
    in the document a chunk lives.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chunk_result_id: uuid.UUID
    ordinal: int
    text: str
    modality: str
    metadata: dict[str, Any] = Field(
        default_factory=dict, validation_alias="chunk_metadata"
    )
    text_normalized: str | None = None


class ChunkSearchHit(BaseModel):
    """A chunk whose text contains the searched string, with the document it comes from."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    ordinal: int
    page: int | None
    text: str


class ChunkResultRead(BaseModel):
    """The state of a chunking artefact.

    Parsing and chunking state is a property of the artefact and not of the document;
    exposing it here rather than on `documents` keeps the API from inventing a status the
    model does not have.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    chunking_configuration_id: uuid.UUID
    parsing_result_id: uuid.UUID
    status: ArtifactStatus
    chunk_count: int
    error: str | None = None
    created_at: dt.datetime


class DocumentChunksRead(BaseModel):
    """One page of the chunks of a document, with the state of the artefact holding them."""

    document_id: uuid.UUID
    chunking_configuration_id: uuid.UUID
    chunk_result: ChunkResultRead
    items: list[ChunkRead] = Field(default_factory=list)
    total: int
    limit: int
    offset: int


class ChunkComparisonSide(BaseModel):
    """The chunks a single configuration produced for the compared document."""

    chunking_configuration_id: uuid.UUID
    chunk_result: ChunkResultRead
    chunks: list[ChunkRead] = Field(default_factory=list)


class ChunkComparisonRead(BaseModel):
    """The same document chunked under two configurations, side by side.

    Not required by the MVP, but it is *the* way to make the premise of the project tangible:
    parsers and chunkers differ exactly where it matters, and a number cannot show that.
    """

    document_id: uuid.UUID
    sides: list[ChunkComparisonSide] = Field(default_factory=list)


class ParsePageRead(BaseModel):
    """The text of one page of a parse."""

    page: int
    text: str


class DocumentParseRead(BaseModel):
    """One window of the per-page text of a parse.

    Paginated by page: this is the diagnostic view for "the chunking looks strange", which
    almost always means "the parse looks strange", and the pages are megabytes of text.
    """

    document_id: uuid.UUID
    parsing_profile_id: uuid.UUID
    parsing_result_id: uuid.UUID
    status: ArtifactStatus
    items: list[ParsePageRead] = Field(default_factory=list)
    total: int
    limit: int
    offset: int
