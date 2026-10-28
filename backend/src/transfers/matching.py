from __future__ import annotations

import dataclasses
import math
import re
import unicodedata
from collections.abc import Mapping, Sequence

from src.infrastructure.database.enums import ConfidenceBand

SEMANTIC = "semantic"
LEXICAL = "lexical"
POSITIONAL = "positional"

# Starting values, not a calibration: they are saved on each job and can be set when it is
# created, so tuning them on a real corpus is a matter of launching another job.
DEFAULT_WEIGHTS = {SEMANTIC: 0.5, LEXICAL: 0.35, POSITIONAL: 0.15}
DEFAULT_THRESHOLDS = {"high": 0.75, "low": 0.45, "preselect": 0.9}

# A chunk this short contained in the reference says little: a page header or a lone
# number is contained in many passages.
_MIN_CONTAINED_TOKENS = 8
_MIN_KEYWORD_LENGTH = 3

_QUOTES = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "‚": "'",
        "‛": "'",
        "“": '"',
        "”": '"',
        "„": '"',
        "«": '"',
        "»": '"',
        "‐": "-",
        "‑": "-",
        "‒": "-",
        "–": "-",
        "—": "-",
        "―": "-",
        "−": "-",
        "|": " ",
        "\t": " ",
        "­": "",
    }
)
# A word split at the end of a line: "infor-\nmazione" is one word.
_HYPHENATED = re.compile(r"(\w)-\s*\n\s*(\w)")
_SPACES = re.compile(r"\s+")
_TOKEN = re.compile(r"\w+")


def normalize(text: str) -> str:
    """Normalise text so the same passage reads the same through different parsers.

    Unicode compatibility forms (ligatures such as "ﬁ"), typographic quotes and dashes,
    soft hyphens, words split across lines, table separators and runs of whitespace are
    the usual differences between two extractions of one PDF; case is dropped too.
    """
    text = unicodedata.normalize("NFKC", text).translate(_QUOTES)
    text = _HYPHENATED.sub(r"\1\2", text)
    return _SPACES.sub(" ", text).strip().lower()


def tokens(text: str) -> list[str]:
    """The words of a text after normalisation."""
    return _TOKEN.findall(normalize(text))


def _ngrams(words: Sequence[str], size: int) -> set[tuple[str, ...]]:
    if len(words) < size:
        return {tuple(words)} if words else set()
    return {tuple(words[i : i + size]) for i in range(len(words) - size + 1)}


def _coverage(of: Sequence[str], within: Sequence[str], size: int) -> float:
    """Share of the word n-grams of `of` that also occur in `within`."""
    wanted = _ngrams(of, size)
    if not wanted:
        return 0.0
    return len(wanted & _ngrams(within, size)) / len(wanted)


def passage_similarity(reference: str, candidate: str) -> float:
    """How much of one passage is the other, from 0 to 1, by word trigrams.

    Symmetric on purpose: a target chunk may hold the whole reference (a larger chunker)
    or be one piece of it (a smaller one), and both are the same evidence. A short
    candidate only counts as contained when it has a few words, so that a header does not
    match every passage that repeats it.
    """
    ref, cand = tokens(reference), tokens(candidate)
    score = _coverage(ref, cand, 3)
    if len(cand) >= _MIN_CONTAINED_TOKENS:
        score = max(score, _coverage(cand, ref, 3))
    return score


def keyword_overlap(reference: str, candidate: str) -> float:
    """Share of the distinct words of the reference that the candidate contains.

    Used when the reference is a question and its answer rather than an extract of the
    document: their wording is not the document's, so passages never match, but the
    names, numbers and terms they share still point at the right chunk.
    """
    wanted = {word for word in tokens(reference) if len(word) >= _MIN_KEYWORD_LENGTH}
    if not wanted:
        return 0.0
    return len(wanted & set(tokens(candidate))) / len(wanted)


def cosine(left: Sequence[float], right: Sequence[float]) -> float:
    """Cosine similarity, 0 when either vector is null."""
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return dot / norm if norm else 0.0


@dataclasses.dataclass(frozen=True)
class Position:
    """Where a chunk is in its document: the page when known, and its relative place."""

    document_id: object
    page: int | None
    relative: float


def relative_position(ordinal: int, count: int) -> float:
    """The place of the middle of a chunk in its document, from 0 to 1.

    The middle rather than the start, so that the same passage gets about the same place
    under chunkers of very different sizes: a large chunk lands where the small chunks it
    contains do, including at the end of the document.
    """
    return (ordinal + 0.5) / count


def positional_score(candidate: Position, sources: Sequence[Position]) -> float:
    """How close a candidate is to the nearest confirmed chunk of the same document.

    Pages are compared when both are known, since they survive a change of chunker;
    otherwise the relative place in the document. A candidate in a document holding no
    confirmed chunk scores 0.
    """
    best = 0.0
    for source in sources:
        if source.document_id != candidate.document_id:
            continue
        if candidate.page is not None and source.page is not None:
            score = 1 / (1 + abs(candidate.page - source.page))
        else:
            score = 1 - min(1.0, abs(candidate.relative - source.relative))
        best = max(best, score)
    return best


def combine(scores: Mapping[str, float | None], weights: Mapping[str, float]) -> float:
    """Weighted mean of the signals that were computed.

    A signal that does not apply (no embedder, or no source to be near) is left out and the
    others are reweighted, rather than counted as 0.
    """
    available = {
        name: value
        for name, value in scores.items()
        if value is not None and weights.get(name, 0) > 0
    }
    total = sum(weights[name] for name in available)
    if not total:
        return 0.0
    return sum(weights[name] * value for name, value in available.items()) / total


def band(combined: float, thresholds: Mapping[str, float]) -> ConfidenceBand:
    if combined >= thresholds["high"]:
        return ConfidenceBand.HIGH
    if combined >= thresholds["low"]:
        return ConfidenceBand.MEDIUM
    return ConfidenceBand.LOW


def preselect(
    lexical: float | None, *, has_source: bool, thresholds: Mapping[str, float]
) -> bool:
    """Whether a candidate is ticked in advance: only a near-identical copy of the source.

    Never without a source: a question and its answer are not an extract of the document,
    so no chunk can be the same text, and a guess must not look like a decision.
    """
    return has_source and lexical is not None and lexical >= thresholds["preselect"]
