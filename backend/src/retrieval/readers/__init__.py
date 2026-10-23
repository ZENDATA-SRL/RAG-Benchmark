from __future__ import annotations

from collections.abc import Callable

from src.components.builtin.contracts import VectorStoreReader

# Aliased: the submodules of this package are also called `chroma` and `qdrant`, and
# importing them rebinds those names on the package.
from src.components.builtin.vector_stores import chroma as chroma_descriptor
from src.components.builtin.vector_stores import qdrant as qdrant_descriptor
from src.retrieval.readers.chroma import build_chroma_reader
from src.retrieval.readers.qdrant import build_qdrant_reader

# Same keys as the worker's write-side map: a vector store an index can be built on must
# also be queryable, which the worker checks at startup.
BUILTIN_VECTOR_STORE_READERS: dict[str, Callable[[], VectorStoreReader]] = {
    chroma_descriptor.KEY: build_chroma_reader,
    qdrant_descriptor.KEY: build_qdrant_reader,
}


def resolve_reader(key: str) -> VectorStoreReader:
    """Return the reader for a vector store component key.

    Raises:
        KeyError: If the key has no reader.
    """
    return BUILTIN_VECTOR_STORE_READERS[key]()
