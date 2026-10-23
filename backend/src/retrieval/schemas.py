from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class RetrieveRequest(BaseModel):
    """A query against one index build, under one retrieval profile."""

    index_build_id: uuid.UUID
    retrieval_profile_id: uuid.UUID
    query: str = Field(min_length=1, max_length=10_000)
    execution_id: uuid.UUID | None = Field(
        default=None,
        description="Experiment execution the call belongs to; absent for a test query.",
    )


class RetrievedHitRead(BaseModel):
    """One retrieved chunk.

    `chunk_id` is null when the vector store returned a vector whose chunk no longer
    exists in the database; `text` then holds what the vector store kept.
    """

    model_config = ConfigDict(from_attributes=True)

    rank: int
    score: float
    stage: str
    chunk_id: uuid.UUID | None
    document_id: uuid.UUID | None
    filename: str | None
    ordinal: int | None
    page: int | None
    text: str | None


class RetrievalTimingsRead(BaseModel):
    """Milliseconds spent embedding the query, searching and reading the chunks back."""

    model_config = ConfigDict(from_attributes=True)

    embed_ms: float
    search_ms: float
    enrich_ms: float
    total_ms: float


class RetrieveResponse(BaseModel):
    """Hits ranked from 1, best first; scores are higher-is-better on every store.

    `corpus_id` and `chunking_configuration_id` are returned so a client can open each hit
    in its document without further lookups.
    """

    model_config = ConfigDict(from_attributes=True)

    index_build_id: uuid.UUID
    retrieval_profile_id: uuid.UUID
    corpus_id: uuid.UUID | None
    chunking_configuration_id: uuid.UUID
    hits: list[RetrievedHitRead]
    timings: RetrievalTimingsRead
