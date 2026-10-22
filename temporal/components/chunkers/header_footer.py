from __future__ import annotations

import re

from src.components.builtin import ParseOutput, ParsePage

# A line that is only digits, or "Page 3", "3 of 12", "- 3 -" and the like: page numbering
# that repeats with a changing number and so never trips the identical-line heuristic.
_PAGE_NUMBER = re.compile(
    r"^\s*(?:page|pag\.?|p\.?)?\s*\d+\s*(?:/|of|di|-|—)?\s*\d*\s*$",
    re.IGNORECASE,
)


def strip_headers_footers(
    parse_output: ParseOutput, *, repetition_threshold: float = 0.6
) -> ParseOutput:
    """Drop repeated page furniture before splitting.

    The heuristic is deliberately **document-local**, as `capabilities.scope = document`
    requires: a corpus-scoped filter would break the per-document scope. A line is furniture when it sits
    in the first or last position of a page and either looks like page numbering or repeats
    identically across at least `repetition_threshold` of the multi-page document.

    The threshold defaults to 0.6 and is a parameter because the right value depends on the
    document: a report with a running title on every page wants a low bar, a book with a
    title only on chapter openings a higher one.

    Returns a new `ParseOutput`; the input is not mutated.
    """
    pages = parse_output["pages"]
    if len(pages) < 2:
        return parse_output

    edge_counts = _count_edge_lines(pages)
    minimum = max(2, int(len(pages) * repetition_threshold))
    repeated = {line for line, count in edge_counts.items() if count >= minimum}

    cleaned: list[ParsePage] = []
    for page in pages:
        cleaned.append(
            ParsePage(page=page["page"], text=_strip_page(page["text"], repeated))
        )
    return ParseOutput(pages=cleaned, metadata=parse_output["metadata"])


def _count_edge_lines(pages: list[ParsePage]) -> dict[str, int]:
    """Count how many pages carry each first/last line, ignoring blanks."""
    counts: dict[str, int] = {}
    for page in pages:
        for line in _edge_lines(page["text"]):
            counts[line] = counts.get(line, 0) + 1
    return counts


def _edge_lines(text: str) -> set[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return set()
    return {lines[0], lines[-1]}


def _strip_page(text: str, repeated: set[str]) -> str:
    lines = text.splitlines()
    start, end = _content_bounds(lines)
    if start > end:
        return ""

    if _is_furniture(lines[start].strip(), repeated):
        start += 1
    if end >= start and _is_furniture(lines[end].strip(), repeated):
        end -= 1
    return "\n".join(lines[start : end + 1]).strip()


def _content_bounds(lines: list[str]) -> tuple[int, int]:
    """Return the indices of the first and last non-blank line."""
    start = 0
    while start < len(lines) and not lines[start].strip():
        start += 1
    end = len(lines) - 1
    while end >= 0 and not lines[end].strip():
        end -= 1
    return start, end


def _is_furniture(line: str, repeated: set[str]) -> bool:
    return bool(line) and (line in repeated or bool(_PAGE_NUMBER.match(line)))
