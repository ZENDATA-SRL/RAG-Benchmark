from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from typing import IO, Any, Protocol, TypedDict, runtime_checkable


class ParsePage(TypedDict):
    """One page of a parsed document."""

    page: int
    text: str


class ParseOutput(TypedDict):
    """What a parser returns, and what gets written to object storage as JSON.

    Kept to `pages` + a free-form `metadata` on purpose: it must be JSON-serialisable
    because the artefact lives on object storage and not in the database, and it
    must survive a re-parse with a different component. A richer parser (Azure DI,
    Docling) adds keys inside `metadata` or extra keys per page without breaking a chunker
    that only reads `pages[].text`.
    """

    pages: list[ParsePage]
    metadata: dict[str, Any]


class ChunkPayload(TypedDict):
    """One chunk as produced by a chunker, before it becomes a `chunks` row.

    The keys are exactly the ones `ArtefactService.complete_chunk_result` consumes, so the
    chunker output needs no adaptation layer on the way to the database.
    """

    text: str
    modality: str
    metadata: dict[str, Any]
    text_normalized: str | None


@runtime_checkable
class Parser(Protocol):
    """A component that turns a binary document into text per page.

    The input is a stream and not bytes so that a large PDF is never fully resident
    .
    """

    def parse(self, stream: IO[bytes], filename: str) -> ParseOutput:
        """Parse a document into its pages."""
        ...


@runtime_checkable
class Chunker(Protocol):
    """A component that splits a parse output into chunks.

    Only document-scoped chunkers exist in v1: the whole caching model keys artefacts on a
    single document's content hash.
    """

    def chunk(
        self, parse_output: ParseOutput, params: dict[str, Any]
    ) -> list[ChunkPayload]:
        """Split a parse output into chunks, honouring the profile parameters."""
        ...


@dataclasses.dataclass(frozen=True)
class VectorHit:
    """One vector returned by a vector store query, before it is enriched from the database.

    `score` is already normalised so that higher means closer, whatever the distance of
    the collection: callers compare and threshold scores without knowing whether the
    index uses cosine, inner product or Euclidean distance.
    """

    id: str
    score: float
    document_id: str | None
    text: str | None


@runtime_checkable
class VectorStoreReader(Protocol):
    """The read side of a vector store: nearest neighbours of a query vector.

    Separate from the write side because they run in different processes: the worker
    writes collections while building an index, the API reads them to answer a query.
    """

    def query(
        self,
        collection: str,
        vector: Sequence[float],
        *,
        top_k: int,
        document_ids: Sequence[str] | None = None,
    ) -> list[VectorHit]:
        """Return the `top_k` closest vectors, best first.

        `document_ids`, when given, restricts the search to vectors of those documents;
        an empty sequence therefore matches nothing.
        """
        ...
