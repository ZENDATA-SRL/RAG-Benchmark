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

from temporal.components.chunkers import markdown, recursive
from temporal.components.embedders.shared import BUILTIN_EMBEDDERS
from temporal.components.parsers import plumber, pypdf
from temporal.components.vector_stores import chroma

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
BUILTIN_VECTOR_STORES: dict[str, Callable[[], chroma.ChromaVectorStore]] = {
    chroma.KEY: chroma.build_chroma_store,
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


def resolve_vector_store(key: str) -> chroma.ChromaVectorStore:
    """Return a vector store client for a component key.

    Raises:
        KeyError: If the key has no implementation.
    """
    return BUILTIN_VECTOR_STORES[key]()


def assert_registry_complete() -> None:
    """Check every declared builtin has an implementation in this worker.

    Called at worker startup. The API can only verify that a key was *declared*; whether it
    is *runnable* is knowable solely here, so this is where the mismatch has to surface —
    at boot, not on the first activity hours into a run.

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
        )
        if descriptor.key not in registry
    ]
    if missing:
        raise RuntimeError(
            f"builtin components declared but not implemented: {', '.join(missing)}"
        )
