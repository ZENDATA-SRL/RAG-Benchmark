from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.components.builtin.chunkers import recursive
from src.components.builtin.contracts import (
    Chunker,
    ChunkPayload,
    ParseOutput,
    ParsePage,
    Parser,
)
from src.components.builtin.parsers import pypdf
from src.infrastructure.database.enums import ComponentType


@dataclass(frozen=True)
class BuiltinDescriptor:
    """What the API knows about a builtin: its identity and its declared contract.

    Only declarative data, deliberately: the descriptors are read by the startup seed and
    served to the UI, which must work in a process that has no parsing library installed
    and no worker running. The code that *executes* the component lives in `temporal/`,
    because the worker is the only process that invokes it.
    """

    component_type: ComponentType
    key: str
    version: str
    display_name: str
    params_schema: dict[str, Any]
    capabilities: dict[str, Any]


PARSER_DESCRIPTORS: tuple[BuiltinDescriptor, ...] = (
    BuiltinDescriptor(
        component_type=ComponentType.PARSER,
        key=pypdf.KEY,
        version=pypdf.VERSION,
        display_name=pypdf.DISPLAY_NAME,
        params_schema=pypdf.PARAMS_SCHEMA,
        capabilities=pypdf.CAPABILITIES,
    ),
)

CHUNKER_DESCRIPTORS: tuple[BuiltinDescriptor, ...] = (
    BuiltinDescriptor(
        component_type=ComponentType.CHUNKER,
        key=recursive.KEY,
        version=recursive.VERSION,
        display_name=recursive.DISPLAY_NAME,
        params_schema=recursive.PARAMS_SCHEMA,
        capabilities=recursive.CAPABILITIES,
    ),
)

BUILTIN_DESCRIPTORS: tuple[BuiltinDescriptor, ...] = PARSER_DESCRIPTORS + CHUNKER_DESCRIPTORS

# Keys declared per type. `register_version` checks a key against this so a registry row can
# never describe a component nobody declared; that the declared key also has an
# implementation is asserted by the worker at startup, which is the only process able to
# tell.
BUILTIN_KEYS: dict[ComponentType, frozenset[str]] = {
    ComponentType.PARSER: frozenset(d.key for d in PARSER_DESCRIPTORS),
    ComponentType.CHUNKER: frozenset(d.key for d in CHUNKER_DESCRIPTORS),
}

__all__ = [
    "BUILTIN_DESCRIPTORS",
    "BUILTIN_KEYS",
    "CHUNKER_DESCRIPTORS",
    "PARSER_DESCRIPTORS",
    "BuiltinDescriptor",
    "ChunkPayload",
    "Chunker",
    "ParseOutput",
    "ParsePage",
    "Parser",
]
