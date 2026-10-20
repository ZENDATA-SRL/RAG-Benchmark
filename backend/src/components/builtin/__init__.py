from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.components.builtin.chunkers import markdown, recursive
from src.components.builtin.contracts import (
    Chunker,
    ChunkPayload,
    ParseOutput,
    ParsePage,
    Parser,
)
from src.components.builtin.embedder import bedrock_embedder, openai_embedder
from src.components.builtin.parsers import pdfplumber, pypdf
from src.components.builtin.vector_stores import chroma, qdrant
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
    BuiltinDescriptor(
        component_type=ComponentType.PARSER,
        key=pdfplumber.KEY,
        version=pdfplumber.VERSION,
        display_name=pdfplumber.DISPLAY_NAME,
        params_schema=pdfplumber.PARAMS_SCHEMA,
        capabilities=pdfplumber.CAPABILITIES,
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
    BuiltinDescriptor(
        component_type=ComponentType.CHUNKER,
        key=markdown.KEY,
        version=markdown.VERSION,
        display_name=markdown.DISPLAY_NAME,
        params_schema=markdown.PARAMS_SCHEMA,
        capabilities=markdown.CAPABILITIES,
    ),
)

EMBEDDER_DESCRIPTORS: tuple[BuiltinDescriptor, ...] = (
    BuiltinDescriptor(
        component_type=ComponentType.EMBEDDER,
        key=openai_embedder.KEY,
        version=openai_embedder.VERSION,
        display_name=openai_embedder.DISPLAY_NAME,
        params_schema=openai_embedder.PARAMS_SCHEMA,
        capabilities={},
    ),
    BuiltinDescriptor(
        component_type=ComponentType.EMBEDDER,
        key=bedrock_embedder.KEY,
        version=bedrock_embedder.VERSION,
        display_name=bedrock_embedder.DISPLAY_NAME,
        params_schema=bedrock_embedder.PARAMS_SCHEMA,
        capabilities={},
    ),
)

VECTOR_STORE_DESCRIPTORS: tuple[BuiltinDescriptor, ...] = (
    BuiltinDescriptor(
        component_type=ComponentType.VECTOR_STORE,
        key=chroma.KEY,
        version=chroma.VERSION,
        display_name=chroma.DISPLAY_NAME,
        params_schema=chroma.PARAMS_SCHEMA,
        capabilities={},
    ),
    BuiltinDescriptor(
        component_type=ComponentType.VECTOR_STORE,
        key=qdrant.KEY,
        version=qdrant.VERSION,
        display_name=qdrant.DISPLAY_NAME,
        params_schema=qdrant.PARAMS_SCHEMA,
        capabilities={},
    ),
)

BUILTIN_DESCRIPTORS: tuple[BuiltinDescriptor, ...] = (
    PARSER_DESCRIPTORS
    + CHUNKER_DESCRIPTORS
    + EMBEDDER_DESCRIPTORS
    + VECTOR_STORE_DESCRIPTORS
)

# Keys declared per type. `register_version` checks a key against this so a registry row can
# never describe a component nobody declared; that the declared key also has an
# implementation is asserted by the worker at startup, which is the only process able to
# tell.
BUILTIN_KEYS: dict[ComponentType, frozenset[str]] = {
    ComponentType.PARSER: frozenset(d.key for d in PARSER_DESCRIPTORS),
    ComponentType.CHUNKER: frozenset(d.key for d in CHUNKER_DESCRIPTORS),
    ComponentType.EMBEDDER: frozenset(d.key for d in EMBEDDER_DESCRIPTORS),
    ComponentType.VECTOR_STORE: frozenset(d.key for d in VECTOR_STORE_DESCRIPTORS),
}

__all__ = [
    "BUILTIN_DESCRIPTORS",
    "BUILTIN_KEYS",
    "CHUNKER_DESCRIPTORS",
    "EMBEDDER_DESCRIPTORS",
    "PARSER_DESCRIPTORS",
    "VECTOR_STORE_DESCRIPTORS",
    "BuiltinDescriptor",
    "ChunkPayload",
    "Chunker",
    "ParseOutput",
    "ParsePage",
    "Parser",
]
