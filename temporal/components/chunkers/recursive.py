from __future__ import annotations

from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter
from src.components.builtin import ChunkPayload, ParseOutput
from src.components.builtin.chunkers import recursive

from temporal.components.chunkers.header_footer import strip_headers_footers
from temporal.components.chunkers.page_mapping import build_paged_text, locate_chunk

KEY = recursive.KEY

_DEFAULT_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]
_HEADER_FOOTER_THRESHOLD = 0.6


class RecursiveChunker:
    """Character-recursive splitting, backed by `langchain-text-splitters`.

    Lives in the worker and not in the API because it is the only process that runs it.
    Satisfies the `Chunker` protocol declared in `src.components.builtin.contracts`.
    """

    def chunk(
        self, parse_output: ParseOutput, params: dict[str, Any]
    ) -> list[ChunkPayload]:
        """Split a parse output into overlapping character chunks, in document order.

        Each chunk carries `metadata: {"page": n, "page_span": [start, end]}`, where the
        page is resolved from the chunk's position in the joined document so the UI can show
        where a chunk came from. Output is deterministic: the same parse and params yield
        the same chunks in the same order, which is what keeps chunk-level gold valid.

        Recognised params (validated upstream against `PARAMS_SCHEMA`): `chunk_size`,
        `overlap`, `separators`, `strip_headers_footers`.
        """
        if params.get("strip_headers_footers", True):
            parse_output = strip_headers_footers(
                parse_output, repetition_threshold=_HEADER_FOOTER_THRESHOLD
            )

        chunker = RecursiveCharacterTextSplitter(
            chunk_size=params["chunk_size"],
            chunk_overlap=params["overlap"],
            separators=params.get("separators", _DEFAULT_SEPARATORS),
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
                    # The parser already emits the canonical normalised form, so the chunk text
                    # is its own normalised form; kept explicit for the lexical matcher.
                    text_normalized=chunk,
                )
            )
        return payloads
