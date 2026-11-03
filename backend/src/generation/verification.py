from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Iterable, Mapping

from src.infrastructure.database.enums import (
    GeneratedKind,
    GenerationPhase,
    RelevanceGrade,
)
from src.transfers.matching import keyword_overlap, normalize, tokens

# Why a submitted question is refused, as the agent is told and the unit counts it.
UNKNOWN_CHUNK = "unknown_chunk"
EMPTY_FIELD = "empty_field"
QUOTE_NOT_IN_CHUNK = "quote_not_in_chunk"
OUTSIDE_DOCUMENT = "outside_document"
SINGLE_DOCUMENT = "single_document"
TOO_MANY_DOCUMENTS = "too_many_documents"
TOO_MANY_CHUNKS = "too_many_chunks"
DUPLICATE = "duplicate"
DISCARD_REASONS = (
    UNKNOWN_CHUNK,
    EMPTY_FIELD,
    QUOTE_NOT_IN_CHUNK,
    OUTSIDE_DOCUMENT,
    SINGLE_DOCUMENT,
    TOO_MANY_DOCUMENTS,
    TOO_MANY_CHUNKS,
    DUPLICATE,
)

# Saved on each job, so a job launched with other values keeps reading them.
DEFAULT_LIMITS = {
    "min_quote_words": 5,
    "max_chunks": 4,
    "min_cross_documents": 2,
    "max_cross_documents": 3,
    "duplicate_overlap": 0.8,
}


@dataclasses.dataclass(frozen=True)
class Citation:
    """A chunk the agent cites by reference, with the passage it quotes from it."""

    ref: str
    quote: str


@dataclasses.dataclass(frozen=True)
class CitedChunk:
    """A cited chunk as the platform resolved it."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    text: str


@dataclasses.dataclass(frozen=True)
class Evidence:
    """A chunk of an accepted submission, with the grade the platform gives it."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    quote: str
    relevance: RelevanceGrade


@dataclasses.dataclass(frozen=True)
class Verdict:
    """Whether a submission is saved, and if so its kind and graded evidence."""

    reason: str | None
    detail: str = ""
    kind: GeneratedKind | None = None
    evidence: list[Evidence] = dataclasses.field(default_factory=list)

    @property
    def accepted(self) -> bool:
        return self.reason is None


def _refuse(reason: str, detail: str) -> Verdict:
    return Verdict(reason=reason, detail=detail)


def is_duplicate(text: str, others: Iterable[str], threshold: float) -> bool:
    """Whether a question says what another one already says, by shared words.

    Measured both ways, so a question contained in a longer one counts too.
    """
    return any(
        max(keyword_overlap(text, other), keyword_overlap(other, text)) >= threshold
        for other in others
    )


def quote_in_chunk(quote: str, chunk_text: str, min_words: int) -> bool:
    """Whether a quote is long enough and found, normalised, in the chunk's text."""
    if len(tokens(quote)) < min_words:
        return False
    return normalize(quote) in normalize(chunk_text)


def verify(
    *,
    question: str,
    answer: str,
    citations: list[Citation],
    resolved: Mapping[str, CitedChunk],
    phase: GenerationPhase,
    unit_document_id: uuid.UUID | None,
    existing: Iterable[str],
    limits: Mapping[str, float],
) -> Verdict:
    """Check a submitted question before it is saved, stopping at the first failure.

    `resolved` maps the references that name a chunk of the job to that chunk; the others
    are unknown. A quote must be found in the chunk it is given for, after normalisation:
    it is never moved to another chunk, so what reaches the review is exactly what the
    agent pointed at, and the agent is told to fix the reference instead.

    The kind and the grades follow from the evidence: one chunk answers on its own and is
    `sufficient`; several chunks only answer together, so all are `supporting`, which is
    how the chunk metrics read evidence without a sufficient chunk.
    """
    limits = {**DEFAULT_LIMITS, **limits}
    if not question.strip() or not answer.strip() or not citations:
        return _refuse(EMPTY_FIELD, "question, answer and citations are all required")

    unique: list[Citation] = []
    for citation in citations:
        if citation.ref.strip().lower() not in {c.ref.strip().lower() for c in unique}:
            unique.append(citation)
    for citation in unique:
        if citation.ref not in resolved:
            return _refuse(UNKNOWN_CHUNK, f"{citation.ref} is not a chunk you can cite")
    for citation in unique:
        chunk = resolved[citation.ref]
        if not quote_in_chunk(
            citation.quote, chunk.text, int(limits["min_quote_words"])
        ):
            return _refuse(
                QUOTE_NOT_IN_CHUNK,
                f"the quote given for {citation.ref} is not in that chunk, or is shorter "
                f"than {int(limits['min_quote_words'])} words; find the chunk that holds "
                "it with find_chunks and copy the passage exactly",
            )

    documents = list(dict.fromkeys(resolved[c.ref].document_id for c in unique))
    if phase is GenerationPhase.DOCUMENT:
        if any(document_id != unit_document_id for document_id in documents):
            return _refuse(OUTSIDE_DOCUMENT, "cite only chunks of this document")
    else:
        if len(documents) < limits["min_cross_documents"]:
            return _refuse(
                SINGLE_DOCUMENT,
                f"the evidence must span at least {int(limits['min_cross_documents'])} "
                "documents",
            )
        if len(documents) > limits["max_cross_documents"]:
            return _refuse(
                TOO_MANY_DOCUMENTS,
                f"the evidence may span at most {int(limits['max_cross_documents'])} "
                "documents",
            )
    if len(unique) > limits["max_chunks"]:
        return _refuse(
            TOO_MANY_CHUNKS, f"cite at most {int(limits['max_chunks'])} chunks"
        )
    if is_duplicate(question, existing, float(limits["duplicate_overlap"])):
        return _refuse(DUPLICATE, "a question like this one already exists")

    if len(documents) > 1:
        kind = GeneratedKind.CROSS
    elif len(unique) > 1:
        kind = GeneratedKind.MULTI
    else:
        kind = GeneratedKind.SINGLE
    relevance = (
        RelevanceGrade.SUFFICIENT
        if kind is GeneratedKind.SINGLE
        else RelevanceGrade.SUPPORTING
    )
    return Verdict(
        reason=None,
        kind=kind,
        evidence=[
            Evidence(
                chunk_id=resolved[c.ref].chunk_id,
                document_id=resolved[c.ref].document_id,
                quote=c.quote.strip(),
                relevance=relevance,
            )
            for c in unique
        ],
    )
