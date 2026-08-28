from __future__ import annotations

from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter
from src.components.builtin import ChunkPayload, ParseOutput
from src.components.builtin.chunkers import recursive

from temporal.components.chunkers.page_mapping import build_paged_text, locate_chunk

KEY = recursive.KEY


class RecursiveChunker:
    """Character-recursive splitting, backed by `langchain-text-splitters`.

    Lives in the worker and not in the API because it is the only process that runs it.
    Satisfies the `Chunker` protocol declared in `src.components.builtin.contracts`.
    """

    def chunk(
        self, parse_output: ParseOutput, params: dict[str, Any]
    ) -> list[ChunkPayload]:
        """Split a parse output into overlapping character chunks.

        Each chunk carries `metadata: {"page": n, "page_span": [start, end]}`, where the
        page is resolved from the chunk's position in the joined document so the UI can
        show where a chunk came from and re-chunking stays deterministic.
        """
        chunker = RecursiveCharacterTextSplitter(
            chunk_size=params["chunk_size"],
            chunk_overlap=params["chunk_overlap"],
        )
        paged = build_paged_text(parse_output)
        chunks = chunker.split_text(paged.text)

        payloads: list[ChunkPayload] = []
        cursor = 0
        for chunk in chunks:
            start, end = locate_chunk(paged, chunk, cursor)
            cursor = start + 1
            first_page, last_page = paged.page_span_for(start, end)
            payloads.append(
                ChunkPayload(
                    text=chunk,
                    modality="text",
                    metadata={"page": first_page, "page_span": [first_page, last_page]},
                    text_normalized=None,
                )
            )
        return payloads
