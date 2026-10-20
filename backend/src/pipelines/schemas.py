from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.infrastructure.database.enums import ArtifactStatus

# --------------------------------------------------------------------------------------
# Profiles
# --------------------------------------------------------------------------------------


class ParsingProfileRead(BaseModel):
    """A parsing profile as exposed by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    component_version_id: uuid.UUID
    params: dict[str, Any] = Field(default_factory=dict)
    config_hash: str
    created_at: dt.datetime


class ChunkingProfileRead(BaseModel):
    """A chunking profile as exposed by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    component_version_id: uuid.UUID
    strategy: str
    chunk_size: int | None = None
    overlap: int | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    config_hash: str
    created_at: dt.datetime


class EmbeddingProfileRead(BaseModel):
    """An embedding profile as exposed by the API."""

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    component_version_id: uuid.UUID
    modality: str
    dimensions: int | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    config_hash: str
    created_at: dt.datetime


class VectorStoreProfileRead(BaseModel):
    """A vector store profile as exposed by the API."""

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    component_version_id: uuid.UUID
    index_params: dict[str, Any] = Field(default_factory=dict)
    config_hash: str
    created_at: dt.datetime

class ParsingProfileCreate(BaseModel):
    """Payload creating a parsing profile."""

    name: str = Field(min_length=1, max_length=200)
    component_version_id: uuid.UUID
    params: dict[str, Any] = Field(default_factory=dict)


class ChunkingProfileCreate(BaseModel):
    """Payload creating a chunking profile.

    `chunk_size` and `overlap` are promoted out of `params` because they are the two knobs
    every chunker has and the ones a listing has to show without opening a JSON blob.
    """

    name: str = Field(min_length=1, max_length=200)
    component_version_id: uuid.UUID
    strategy: str = Field(min_length=1, max_length=100)
    chunk_size: int | None = Field(default=None, ge=1)
    overlap: int | None = Field(default=None, ge=0)
    params: dict[str, Any] = Field(default_factory=dict)


class EmbeddingProfileCreate(BaseModel):
    """Payload creating an embedding profile."""

    name: str = Field(min_length=1, max_length=200)
    component_version_id: uuid.UUID
    modality: str = Field(min_length=1, max_length=100)
    dimensions: int | None = Field(default=None, ge=1)
    params: dict[str, Any] = Field(default_factory=dict)


class DeduplicatedRead(BaseModel):
    """Base for responses that must confess a get-or-create.

    `created` is not decoration: the profile tables deduplicate on the hash of the
    behaviour and exclude the name from it (RF-P07), so asking for a profile that already
    exists under another name returns the original row. Saying so is the only way the user
    can understand why the name they typed is not the one they got back.
    """

    created: bool
    detail: str | None = None


class ParsingProfileCreated(DeduplicatedRead):
    """A parsing profile with the outcome of the get-or-create that returned it."""

    profile: ParsingProfileRead


class ChunkingProfileCreated(DeduplicatedRead):
    """A chunking profile with the outcome of the get-or-create that returned it."""

    profile: ChunkingProfileRead
    
class EmbeddingProfileCreated(DeduplicatedRead):
    """An embedding profile with the outcome of the get-or-create that returned it."""

    profile: EmbeddingProfileRead


# --------------------------------------------------------------------------------------
# Chunking configurations
# --------------------------------------------------------------------------------------


class ChunkingConfigurationRead(BaseModel):
    """A chunking configuration as exposed by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    parsing_profile_id: uuid.UUID
    chunking_profile_id: uuid.UUID
    config_hash: str
    created_at: dt.datetime


class ChunkingConfigurationExpanded(ChunkingConfigurationRead):
    """A configuration with its two profiles inlined.

    Expanded server-side so the UI can label a row "pypdf + recursive512" in one call
    instead of three.
    """

    parsing_profile: ParsingProfileRead
    chunking_profile: ChunkingProfileRead


class ChunkingConfigurationCreate(BaseModel):
    """Payload creating a configuration from two existing profiles."""

    parsing_profile_id: uuid.UUID
    chunking_profile_id: uuid.UUID
    name: str | None = Field(default=None, min_length=1, max_length=200)


class ChunkingConfigurationCreated(DeduplicatedRead):
    """A configuration with the outcome of the get-or-create that returned it."""

    configuration: ChunkingConfigurationExpanded


class ChunkingConfigurationCompose(BaseModel):
    """Payload composing a configuration from two profiles given by value.

    The shortcut behind a single UI form; the granular endpoints stay for anything that
    references an existing profile by id.
    """

    parsing_component_version_id: uuid.UUID
    parsing_profile_name: str = Field(min_length=1, max_length=200)
    parsing_params: dict[str, Any] = Field(default_factory=dict)

    chunking_component_version_id: uuid.UUID
    chunking_profile_name: str = Field(min_length=1, max_length=200)
    chunking_strategy: str = Field(min_length=1, max_length=100)
    chunk_size: int | None = Field(default=None, ge=1)
    overlap: int | None = Field(default=None, ge=0)
    chunking_params: dict[str, Any] = Field(default_factory=dict)

    name: str | None = Field(default=None, min_length=1, max_length=200)


class ChunkingConfigurationComposed(BaseModel):
    """Result of composing a configuration, one `created` flag per row involved."""

    configuration: ChunkingConfigurationExpanded
    created: bool
    parsing_profile_created: bool
    chunking_profile_created: bool
    detail: str | None = None


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
# Materialisation
# --------------------------------------------------------------------------------------


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


# --------------------------------------------------------------------------------------
# Inspection
# --------------------------------------------------------------------------------------


class ChunkRead(BaseModel):
    """A chunk as exposed by the API.

    `metadata` carries the page the chunk came from, which is what lets the UI show *where*
    in the document a chunk lives (RT-U04).
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chunk_result_id: uuid.UUID
    ordinal: int
    text: str
    modality: str
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="chunk_metadata")
    text_normalized: str | None = None


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


# --------------------------------------------------------------------------------------
# Index builds
# --------------------------------------------------------------------------------------


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
