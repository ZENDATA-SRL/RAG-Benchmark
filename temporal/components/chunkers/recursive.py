from __future__ import annotations

from typing import Any

from src.components.builtin import ChunkPayload, ParseOutput
from src.components.builtin.chunkers import recursive

KEY = recursive.KEY


class RecursiveChunker:
    """Character-recursive splitting, backed by `langchain-text-splitters`.

    Lives in the worker and not in the API because it is the only process that runs it.
    Satisfies the `Chunker` protocol declared in `src.components.builtin.contracts`.
    """

    def chunk(self, parse_output: ParseOutput, params: dict[str, Any]) -> list[ChunkPayload]:
        """Split a parse output into overlapping character chunks.

        Raises:
            NotImplementedError: Until the chunking activity of Sprint 3 lands.
        """
        raise NotImplementedError(
            "RecursiveChunker.chunk lands with the Sprint 3 chunking activity"
        )
