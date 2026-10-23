from __future__ import annotations

from collections.abc import Callable

from src.components.builtin import (
    CHUNKER_DESCRIPTORS,
    EMBEDDER_DESCRIPTORS,
    PARSER_DESCRIPTORS,
    VECTOR_STORE_DESCRIPTORS,
    Chunker,
    Parser,
)
from src.retrieval.embedders import BUILTIN_EMBEDDERS
from src.retrieval.readers import BUILTIN_VECTOR_STORE_READERS

from temporal.components.chunkers import markdown, recursive
from temporal.components.parsers import plumber, pypdf
from temporal.components.vector_stores import chroma, qdrant

# `builtin` means exactly this: the key maps to a class in this repository, invoked
# in-process by the worker with no network hop.
BUILTIN_PARSERS: dict[str, Parser] = {
    pypdf.KEY: pypdf.PyPdfParser(),
    plumber.KEY: plumber.PdfPlumberParser(),
}
BUILTIN_CHUNKERS: dict[str, Chunker] = {
    recursive.KEY: recursive.RecursiveChunker(),
    markdown.KEY: markdown.MarkdownChunker(),
}
# A factory, because the store client is bound to the server in the settings and should
# only be built inside an activity.
VectorStore = chroma.ChromaVectorStore | qdrant.QdrantVectorStore
BUILTIN_VECTOR_STORES: dict[str, Callable[[], VectorStore]] = {
    chroma.KEY: chroma.build_chroma_store,
    qdrant.KEY: qdrant.build_qdrant_store,
}


def resolve_parser(key: str) -> Parser:
    """Return the parser implementation for a component key.

    Raises:
        KeyError: If the key has no implementation, which means a registry row was created
            for a component this worker cannot execute.
    """
    return BUILTIN_PARSERS[key]


def resolve_chunker(key: str) -> Chunker:
    """Return the chunker implementation for a component key.

    Raises:
        KeyError: If the key has no implementation.
    """
    return BUILTIN_CHUNKERS[key]


def resolve_vector_store(key: str) -> VectorStore:
    """Return a vector store client for a component key.

    Raises:
        KeyError: If the key has no implementation.
    """
    return BUILTIN_VECTOR_STORES[key]()


def assert_registry_complete() -> None:
    """Check every declared builtin has an implementation in this worker.

    Called at worker startup. The API can only verify that a key was *declared*; whether it
    is *runnable* is knowable solely here, so this is where the mismatch has to surface —
    at boot, not on the first activity hours into a run. A vector store must also have a
    reader: an index the API cannot query would be built for nothing.

    Raises:
        RuntimeError: If a descriptor has no matching implementation.
    """
    missing = [
        f"{descriptor.component_type.value}/{descriptor.key}"
        for descriptor, registry in (
            *((d, BUILTIN_PARSERS) for d in PARSER_DESCRIPTORS),
            *((d, BUILTIN_CHUNKERS) for d in CHUNKER_DESCRIPTORS),
            *((d, BUILTIN_EMBEDDERS) for d in EMBEDDER_DESCRIPTORS),
            *((d, BUILTIN_VECTOR_STORES) for d in VECTOR_STORE_DESCRIPTORS),
            *((d, BUILTIN_VECTOR_STORE_READERS) for d in VECTOR_STORE_DESCRIPTORS),
        )
        if descriptor.key not in registry
    ]
    if missing:
        raise RuntimeError(
            f"builtin components declared but not implemented: {', '.join(missing)}"
        )
