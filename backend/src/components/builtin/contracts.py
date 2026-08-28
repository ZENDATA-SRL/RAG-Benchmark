from __future__ import annotations

from typing import IO, Any, Protocol, TypedDict, runtime_checkable


class ParsePage(TypedDict):
    """One page of a parsed document."""

    page: int
    text: str


class ParseOutput(TypedDict):
    """What a parser returns, and what gets written to object storage as JSON.

    Kept to `pages` + a free-form `metadata` on purpose: it must be JSON-serialisable
    because the artefact lives on object storage and not in the database (RT-O02), and it
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

    def chunk(self, parse_output: ParseOutput, params: dict[str, Any]) -> list[ChunkPayload]:
        """Split a parse output into chunks, honouring the profile parameters."""
        ...
