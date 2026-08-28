from __future__ import annotations

from src.components.builtin import (
    CHUNKER_DESCRIPTORS,
    PARSER_DESCRIPTORS,
    Chunker,
    Parser,
)
from temporal.components.chunkers import recursive
from temporal.components.parsers import pypdf

# `builtin` means exactly this: the key maps to a class in this repository, invoked
# in-process by the worker with no network hop.
BUILTIN_PARSERS: dict[str, Parser] = {pypdf.KEY: pypdf.PyPdfParser()}
BUILTIN_CHUNKERS: dict[str, Chunker] = {recursive.KEY: recursive.RecursiveChunker()}


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
        )
        if descriptor.key not in registry
    ]
    if missing:
        raise RuntimeError(f"builtin components declared but not implemented: {', '.join(missing)}")
