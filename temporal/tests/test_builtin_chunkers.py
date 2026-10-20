from __future__ import annotations

from src.components.builtin import ParseOutput, ParsePage

from temporal.components.chunkers.markdown import MarkdownChunker
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


def test_markdown_prefers_heading_boundaries() -> None:
    """A heading is a stronger split point than a mid-paragraph character cut."""
    body = "word " * 30
    text = f"# Title\n\n{body}\n\n## Section A\n\n{body}\n\n## Section B\n\n{body}"
    chunks = MarkdownChunker().chunk(
        _parse_output([text]),
        {"chunk_size": 180, "overlap": 0, "strip_headers_footers": False},
    )
    assert len(chunks) > 1
    assert all(len(chunk["text"]) <= 180 for chunk in chunks)
    headings_at_start = [
        chunk["text"].lstrip().startswith("#") or chunk["text"].lstrip().startswith("##")
        for chunk in chunks[1:]
    ]
    assert any(headings_at_start)


def test_markdown_is_deterministic() -> None:
    chunker = MarkdownChunker()
    parse = _parse_output(["# Alpha\n\n" + "beta gamma. " * 30, "## Delta\n\n" + "epsilon. " * 30])
    params = {"chunk_size": 120, "overlap": 20, "strip_headers_footers": False}
    assert chunker.chunk(parse, params) == chunker.chunk(parse, params)


def test_markdown_propagates_page_metadata() -> None:
    chunker = MarkdownChunker()
    parse = _parse_output(["# Page one\n\nContent.", "## Page two\n\nMore content."])
    chunks = chunker.chunk(
        parse, {"chunk_size": 20, "overlap": 0, "strip_headers_footers": False}
    )
    pages = {chunk["metadata"]["page"] for chunk in chunks}
    assert pages == {1, 2}
    for chunk in chunks:
        assert "page_span" in chunk["metadata"]
        assert chunk["text_normalized"] == chunk["text"]


def test_markdown_attaches_header_metadata_and_keeps_headings() -> None:
    """Default `strip_headers=False` leaves the heading in the text and in metadata."""
    text = "# Title\n\nIntro paragraph.\n\n## Section A\n\nBody of A.\n\n### Detail\n\nNested."
    chunks = MarkdownChunker().chunk(
        _parse_output([text]),
        {"chunk_size": 1000, "overlap": 0, "strip_headers_footers": False},
    )
    assert len(chunks) >= 2
    assert any(chunk["text"].lstrip().startswith("#") for chunk in chunks)
    assert any(chunk["metadata"].get("Header 1") == "Title" for chunk in chunks)
    assert any(chunk["metadata"].get("Header 2") == "Section A" for chunk in chunks)


def test_markdown_strip_headers_drops_heading_lines() -> None:
    text = "# Title\n\nIntro paragraph.\n\n## Section A\n\nBody of A."
    chunks = MarkdownChunker().chunk(
        _parse_output([text]),
        {
            "chunk_size": 1000,
            "overlap": 0,
            "strip_headers_footers": False,
            "strip_headers": True,
        },
    )
    joined = "\n".join(chunk["text"] for chunk in chunks)
    assert "# Title" not in joined
    assert "## Section A" not in joined
    assert any(chunk["metadata"].get("Header 1") == "Title" for chunk in chunks)


def test_markdown_page_span_survives_rewritten_whitespace() -> None:
    # MarkdownHeaderTextSplitter rewrites line breaks, so a chunk is not an exact substring
    # of the joined pages; the span must still follow the chunk through the document.
    pages = [
        "\n".join(f"Page {number} line {line} some words here" for line in range(6))
        for number in range(1, 7)
    ]
    chunks = MarkdownChunker().chunk(
        _parse_output(pages),
        {"chunk_size": 300, "overlap": 0, "strip_headers_footers": False},
    )
    firsts = [chunk["metadata"]["page"] for chunk in chunks]
    assert firsts == sorted(firsts)
    assert firsts[0] == 1
    assert chunks[-1]["metadata"]["page_span"][1] == 6
    assert max(firsts) > 3
