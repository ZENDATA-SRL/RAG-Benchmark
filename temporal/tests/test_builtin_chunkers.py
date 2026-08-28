from __future__ import annotations

from src.components.builtin import ParseOutput, ParsePage

from temporal.components.chunkers.recursive import RecursiveChunker


def _parse_output(pages: list[str]) -> ParseOutput:
    return ParseOutput(
        pages=[ParsePage(page=index, text=text) for index, text in enumerate(pages, start=1)],
        metadata={"page_count": len(pages), "producer": None},
    )


def test_respects_chunk_size() -> None:
    chunker = RecursiveChunker()
    text = " ".join(f"word{i}" for i in range(200))
    chunks = chunker.chunk(
        _parse_output([text]),
        {"chunk_size": 100, "overlap": 0, "strip_headers_footers": False},
    )
    assert len(chunks) > 1
    assert all(len(chunk["text"]) <= 100 for chunk in chunks)


def test_is_deterministic() -> None:
    chunker = RecursiveChunker()
    parse = _parse_output(["Alpha beta gamma. " * 30, "Delta epsilon zeta. " * 30])
    params = {"chunk_size": 120, "overlap": 20, "strip_headers_footers": False}
    first = chunker.chunk(parse, params)
    second = chunker.chunk(parse, params)
    assert first == second


def test_propagates_page_metadata() -> None:
    chunker = RecursiveChunker()
    parse = _parse_output(["Page one content.", "Page two content."])
    chunks = chunker.chunk(
        parse, {"chunk_size": 18, "overlap": 0, "strip_headers_footers": False}
    )
    pages = {chunk["metadata"]["page"] for chunk in chunks}
    assert pages == {1, 2}
    for chunk in chunks:
        assert "page_span" in chunk["metadata"]
        assert chunk["text_normalized"] == chunk["text"]


def test_strips_repeated_header() -> None:
    """A running header on every page is dropped when the filter is on, kept when off."""
    header = "CONFIDENTIAL REPORT"
    pages = [f"{header}\nUnique body of page {i}." for i in range(1, 6)]
    parse = _parse_output(pages)

    with_strip = RecursiveChunker().chunk(
        parse, {"chunk_size": 1000, "overlap": 0, "strip_headers_footers": True}
    )
    without_strip = RecursiveChunker().chunk(
        parse, {"chunk_size": 1000, "overlap": 0, "strip_headers_footers": False}
    )

    joined_stripped = " ".join(chunk["text"] for chunk in with_strip)
    joined_kept = " ".join(chunk["text"] for chunk in without_strip)
    assert header not in joined_stripped
    assert header in joined_kept
