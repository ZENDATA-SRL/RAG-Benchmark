from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.infrastructure.database.enums import RetrievalStrategy

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


class RetrievalProfileRead(BaseModel):
    """A retrieval profile as exposed by the API: the fields the engine applies today."""

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    top_k: int
    strategy: RetrievalStrategy
    score_threshold: float | None = None
    metadata_filters: dict[str, Any] | None = None
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


class VectorStoreProfileCreate(BaseModel):
    """Payload creating a vector store profile."""

    name: str = Field(min_length=1, max_length=200)
    component_version_id: uuid.UUID
    index_params: dict[str, Any] = Field(default_factory=dict)


class RetrievalProfileCreate(BaseModel):
    """Payload creating a retrieval profile.

    Only `dense` is executable today; the other strategies are refused with a `422`.
    `metadata_filters` matches the user metadata of the documents: a document qualifies
    when its metadata contains every key with the given value.
    """

    name: str = Field(min_length=1, max_length=200)
    top_k: int = Field(ge=1, le=200)
    strategy: RetrievalStrategy = RetrievalStrategy.DENSE
    score_threshold: float | None = None
    metadata_filters: dict[str, Any] | None = None


class DeduplicatedRead(BaseModel):
    """Base for responses that must confess a get-or-create.

    `created` is not decoration: the profile tables deduplicate on the hash of the
    behaviour and exclude the name from it, so asking for a profile that already
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


class VectorStoreProfileCreated(DeduplicatedRead):
    """A vector store profile with the outcome of the get-or-create that returned it."""

    profile: VectorStoreProfileRead


class RetrievalProfileCreated(DeduplicatedRead):
    """A retrieval profile with the outcome of the get-or-create that returned it."""

    profile: RetrievalProfileRead


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
