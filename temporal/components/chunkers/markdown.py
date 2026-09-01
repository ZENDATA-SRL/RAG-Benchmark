from __future__ import annotations

from typing import Any

from langchain_text_splitters import MarkdownHeaderTextSplitter, MarkdownTextSplitter
from src.components.builtin import ChunkPayload, ParseOutput
from src.components.builtin.chunkers import markdown

from temporal.components.chunkers.header_footer import strip_headers_footers
from temporal.components.chunkers.page_mapping import build_paged_text, locate_chunk

KEY = markdown.KEY

_HEADER_FOOTER_THRESHOLD = 0.6
_DEFAULT_HEADERS_TO_SPLIT_ON: list[tuple[str, str]] = [
    ("#", "Header 1"),
    ("##", "Header 2"),
    ("###", "Header 3"),
]


def _headers_to_split_on(params: dict[str, Any]) -> list[tuple[str, str]]:
    raw = params.get("headers_to_split_on", _DEFAULT_HEADERS_TO_SPLIT_ON)
    return [(str(marker), str(name)) for marker, name in raw]


class MarkdownChunker:
    """Markdown-aware splitting, backed by `langchain-text-splitters`.

    Lives in the worker and not in the API because it is the only process that runs it.
    Satisfies the `Chunker` protocol declared in `src.components.builtin.contracts`.
    """

    def chunk(
        self, parse_output: ParseOutput, params: dict[str, Any]
    ) -> list[ChunkPayload]:
        """Split a parse output on Markdown headings, then by size, in document order.

        `MarkdownHeaderTextSplitter` cuts on the configured heading markers and writes
        those headings into chunk metadata. Sections that still exceed `chunk_size` are
        broken up by `MarkdownTextSplitter`. Each chunk also carries
        `metadata: {"page": n, "page_span": [start, end]}`. Output is deterministic.

        Recognised params (validated upstream against `PARAMS_SCHEMA`): `chunk_size`,
        `overlap`, `strip_headers_footers`, `headers_to_split_on`, `strip_headers`.
        """
        if params.get("strip_headers_footers", True):
            parse_output = strip_headers_footers(
                parse_output, repetition_threshold=_HEADER_FOOTER_THRESHOLD
            )

        paged = build_paged_text(parse_output)
        header_docs = MarkdownHeaderTextSplitter(
            headers_to_split_on=_headers_to_split_on(params),
            strip_headers=params.get("strip_headers", False),
        ).split_text(paged.text)

        size_splitter = MarkdownTextSplitter(
            chunk_size=params["chunk_size"],
            chunk_overlap=params["overlap"],
            # The class supplies regex separators (`\n#{1,6} `, fences, rules) but does
            # not set this flag; without it they are treated as literals and never match.
            is_separator_regex=True,
        )
        docs = size_splitter.split_documents(header_docs)

        payloads: list[ChunkPayload] = []
        cursor = 0
        for doc in docs:
            chunk = doc.page_content
            start, end = locate_chunk(paged, chunk, cursor)
            cursor = start + 1
            first_page, last_page = paged.page_span_for(start, end)
            payloads.append(
                ChunkPayload(
                    text=chunk,
                    modality="text",
                    metadata={
                        **doc.metadata,
                        "page": first_page,
                        "page_span": [first_page, last_page],
                    },
                    text_normalized=chunk,
                )
            )
        return payloads
