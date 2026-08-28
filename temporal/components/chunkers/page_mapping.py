from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass

from src.components.builtin import ParseOutput


@dataclass(frozen=True)
class PagedText:
    """The concatenation of a parse output's pages plus their character offsets.

    `page_starts[i]` is the index in `text` where page `page_numbers[i]` begins, so a
    chunk's character offset can be resolved back to the page(s) it came from without the
    splitter having to know anything about pages.
    """

    text: str
    page_starts: list[int]
    page_numbers: list[int]

    def page_span_for(self, start: int, end: int) -> tuple[int, int]:
        """Return the ``(first_page, last_page)`` a ``[start, end)`` slice touches.

        ``end`` is exclusive; an empty slice is treated as covering the page at ``start``.
        Offsets past the text are clamped to the last page so a caller never gets an
        out-of-range page number.
        """
        last = max(start, end - 1)
        first_page = self._page_at(start)
        last_page = self._page_at(last)
        return first_page, last_page

    def _page_at(self, offset: int) -> int:
        index = bisect_right(self.page_starts, offset) - 1
        index = min(max(index, 0), len(self.page_numbers) - 1)
        return self.page_numbers[index]


def build_paged_text(parse_output: ParseOutput, separator: str = "\n\n") -> PagedText:
    """Join the pages into one string while recording where each page starts.

    The separator is inserted between pages only, so it never appears at the very start
    and the recorded offsets always point at real page content.
    """
    pieces: list[str] = []
    page_starts: list[int] = []
    page_numbers: list[int] = []
    cursor = 0
    for position, page in enumerate(parse_output["pages"]):
        if position > 0:
            pieces.append(separator)
            cursor += len(separator)
        page_starts.append(cursor)
        page_numbers.append(page["page"])
        text = page["text"]
        pieces.append(text)
        cursor += len(text)
    return PagedText(
        text="".join(pieces),
        page_starts=page_starts,
        page_numbers=page_numbers,
    )


def locate_chunk(paged: PagedText, chunk: str, search_from: int) -> tuple[int, int]:
    """Find where ``chunk`` sits in ``paged.text`` at or after ``search_from``.

    Chunkers emit their output in document order, so a running cursor makes the lookup
    linear and unambiguous even when the same text repeats. When the splitter has stripped
    whitespace and the chunk is no longer an exact substring, we fall back to the search
    cursor so the chunk is still attributed to a plausible position rather than dropped.

    Returns the ``[start, end)`` offsets of the chunk in the joined text.
    """
    start = paged.text.find(chunk, search_from)
    if start == -1:
        start = min(search_from, len(paged.text))
    return start, start + len(chunk)
