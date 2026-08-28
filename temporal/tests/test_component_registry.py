from __future__ import annotations

import pytest

from src.components.builtin import (
    BUILTIN_DESCRIPTORS,
    CHUNKER_DESCRIPTORS,
    PARSER_DESCRIPTORS,
    Chunker,
    Parser,
)
from temporal.components import (
    BUILTIN_CHUNKERS,
    BUILTIN_PARSERS,
    assert_registry_complete,
    resolve_chunker,
    resolve_parser,
)


def test_every_declared_builtin_has_an_implementation() -> None:
    """The invariant the three-way split rests on: descriptors and code must not drift.

    The API declares components without importing their code, so nothing at import time
    catches a descriptor whose implementation was never written. This test is that check.
    """
    assert_registry_complete()


def test_no_implementation_without_a_descriptor() -> None:
    """The reverse direction: code nobody declared would never be reachable via the registry."""
    declared_parsers = {descriptor.key for descriptor in PARSER_DESCRIPTORS}
    declared_chunkers = {descriptor.key for descriptor in CHUNKER_DESCRIPTORS}

    assert set(BUILTIN_PARSERS) == declared_parsers
    assert set(BUILTIN_CHUNKERS) == declared_chunkers


def test_implementations_satisfy_their_protocols() -> None:
    """`Parser` and `Chunker` are runtime-checkable, so the shape is verifiable here."""
    for implementation in BUILTIN_PARSERS.values():
        assert isinstance(implementation, Parser)
    for implementation in BUILTIN_CHUNKERS.values():
        assert isinstance(implementation, Chunker)


def test_resolve_parser_returns_the_implementation() -> None:
    for descriptor in PARSER_DESCRIPTORS:
        assert resolve_parser(descriptor.key) is BUILTIN_PARSERS[descriptor.key]


def test_resolve_chunker_returns_the_implementation() -> None:
    for descriptor in CHUNKER_DESCRIPTORS:
        assert resolve_chunker(descriptor.key) is BUILTIN_CHUNKERS[descriptor.key]


def test_resolving_an_unknown_key_raises() -> None:
    with pytest.raises(KeyError):
        resolve_parser("not-a-parser")


def test_descriptors_are_unique_per_type_and_key() -> None:
    """A duplicate would make the seed's get-or-create write the second over the first."""
    identities = [
        (descriptor.component_type, descriptor.key) for descriptor in BUILTIN_DESCRIPTORS
    ]
    assert len(identities) == len(set(identities))
