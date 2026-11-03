from __future__ import annotations

import uuid

from src.generation.refs import Refs
from src.generation.verification import (
    DUPLICATE,
    EMPTY_FIELD,
    OUTSIDE_DOCUMENT,
    QUOTE_NOT_IN_CHUNK,
    SINGLE_DOCUMENT,
    TOO_MANY_CHUNKS,
    TOO_MANY_DOCUMENTS,
    UNKNOWN_CHUNK,
    Citation,
    CitedChunk,
    verify,
)
from src.generation.zones import zone_of, zones
from src.infrastructure.database.enums import (
    GeneratedKind,
    GenerationPhase,
    RelevanceGrade,
)

D1, D2, D3, D4 = (uuid.uuid4() for _ in range(4))
TEXT = (
    "La penale per ritardo nella con-\nsegna è pari all’1 per mille dell’importo "
    "contrattuale per ogni giorno di ritardo."
)
QUOTE = "La penale per ritardo nella consegna è pari all'1 per mille"


def _chunk(document_id: uuid.UUID, text: str = TEXT) -> CitedChunk:
    return CitedChunk(uuid.uuid4(), document_id, text)


def _verify(citations, resolved, *, phase=GenerationPhase.DOCUMENT, **overrides):
    return verify(
        question=overrides.pop("question", "Quanto costa il ritardo?"),
        answer=overrides.pop("answer", "L'1 per mille."),
        citations=citations,
        resolved=resolved,
        phase=phase,
        unit_document_id=D1 if phase is GenerationPhase.DOCUMENT else None,
        existing=overrides.pop("existing", []),
        limits=overrides.pop("limits", {}),
    )


def test_one_chunk_is_a_single_sufficient_question():
    chunk = _chunk(D1)
    verdict = _verify([Citation("d1:c0", QUOTE)], {"d1:c0": chunk})
    assert verdict.accepted
    assert verdict.kind is GeneratedKind.SINGLE
    assert [(e.chunk_id, e.relevance) for e in verdict.evidence] == [
        (chunk.chunk_id, RelevanceGrade.SUFFICIENT)
    ]


def test_quote_is_matched_after_normalisation_but_never_moved():
    assert _verify([Citation("d1:c0", QUOTE)], {"d1:c0": _chunk(D1)}).accepted
    other = _chunk(D1, "Le fatture sono pagate a sessanta giorni dalla ricezione.")
    verdict = _verify([Citation("d1:c1", QUOTE)], {"d1:c1": other})
    assert verdict.reason == QUOTE_NOT_IN_CHUNK


def test_short_quote_is_refused():
    verdict = _verify([Citation("d1:c0", "La penale")], {"d1:c0": _chunk(D1)})
    assert verdict.reason == QUOTE_NOT_IN_CHUNK


def test_empty_fields_and_unknown_chunks():
    assert _verify([], {}).reason == EMPTY_FIELD
    assert _verify([Citation("d1:c0", QUOTE)], {}, answer=" ").reason == EMPTY_FIELD
    assert _verify([Citation("d1:c7", QUOTE)], {}).reason == UNKNOWN_CHUNK


def test_document_phase_keeps_to_its_document():
    verdict = _verify([Citation("d2:c0", QUOTE)], {"d2:c0": _chunk(D2)})
    assert verdict.reason == OUTSIDE_DOCUMENT


def test_several_chunks_of_one_document_are_supporting():
    resolved = {"d1:c0": _chunk(D1), "d1:c1": _chunk(D1)}
    verdict = _verify(
        [Citation("d1:c0", QUOTE), Citation("d1:c1", QUOTE), Citation("D1:C0", QUOTE)],
        {**resolved, "D1:C0": resolved["d1:c0"]},
    )
    assert verdict.kind is GeneratedKind.MULTI
    assert len(verdict.evidence) == 2
    assert {e.relevance for e in verdict.evidence} == {RelevanceGrade.SUPPORTING}


def test_cross_needs_two_to_three_documents():
    cross = GenerationPhase.CROSS
    one = _verify([Citation("d1:c0", QUOTE)], {"d1:c0": _chunk(D1)}, phase=cross)
    assert one.reason == SINGLE_DOCUMENT
    two = {"d1:c0": _chunk(D1), "d2:c0": _chunk(D2)}
    verdict = _verify([Citation(ref, QUOTE) for ref in two], two, phase=cross)
    assert verdict.kind is GeneratedKind.CROSS
    four = {f"d{i}:c0": _chunk(d) for i, d in enumerate((D1, D2, D3, D4), start=1)}
    many = _verify([Citation(ref, QUOTE) for ref in four], four, phase=cross)
    assert many.reason == TOO_MANY_DOCUMENTS


def test_too_many_chunks():
    resolved = {f"d1:c{i}": _chunk(D1) for i in range(5)}
    verdict = _verify([Citation(ref, QUOTE) for ref in resolved], resolved)
    assert verdict.reason == TOO_MANY_CHUNKS


def test_duplicates_are_measured_both_ways():
    citations, resolved = [Citation("d1:c0", QUOTE)], {"d1:c0": _chunk(D1)}
    existing = ["Quanto costa il ritardo nella consegna dei servizi?"]
    assert _verify(citations, resolved, existing=existing).reason == DUPLICATE
    assert _verify(citations, resolved, existing=["Chi firma il verbale?"]).accepted


def test_refs_resolve_only_documents_of_the_job():
    refs = Refs([D1, D2])
    assert refs.document(D2) == "d2"
    assert refs.chunk(D1, 12) == "d1:c12"
    assert refs.resolve_chunk(" D2:C3 ") == (D2, 3)
    assert refs.resolve_chunk("d3:c0") is None
    assert refs.resolve_chunk("c3") is None
    assert refs.resolve_document("d0") is None


def test_zones_cover_the_document_evenly():
    assert zones(10, 3) == [range(4), range(4, 7), range(7, 10)]
    assert zones(2, 5) == [range(1), range(1, 2)]
    assert zones(0, 3) == []
    split = zones(10, 3)
    assert [zone_of(o, split) for o in (0, 4, 9)] == [1, 2, 3]
    assert zone_of(12, split) is None
