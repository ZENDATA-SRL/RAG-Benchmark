from __future__ import annotations

import pytest
from src.infrastructure.database.enums import ConfidenceBand
from src.transfers.matching import (
    DEFAULT_THRESHOLDS,
    DEFAULT_WEIGHTS,
    LEXICAL,
    POSITIONAL,
    SEMANTIC,
    Position,
    band,
    combine,
    cosine,
    keyword_overlap,
    normalize,
    passage_similarity,
    positional_score,
    preselect,
    relative_position,
)

PASSAGE = (
    "La penale per ritardo nella consegna è pari all'1 per mille dell'importo "
    "contrattuale per ogni giorno lavorativo di ritardo, fino al 10 per cento."
)


def test_normalisation_removes_what_two_parsers_disagree_on() -> None:
    assert normalize("“Efﬁcienza” – infor-\nmazione­le |  tabella\t A") == (
        '"efficienza" - informazionele tabella a'
    )


def test_the_same_passage_from_another_extraction_matches_almost_exactly() -> None:
    # Ligature, typographic apostrophes and dashes, a word split across lines and a
    # different line layout: what a second parser typically returns.
    other = (
        "La penale per ritardo nella con-\nsegna è pari all’1 per mille dell’importo\n"
        "contrattuale per ogni giorno lavorativo di ritardo, ﬁno al 10 per cento."
    )

    assert passage_similarity(PASSAGE, other) >= 0.95


def test_a_piece_of_the_reference_counts_as_the_same_evidence() -> None:
    piece = "pari all'1 per mille dell'importo contrattuale per ogni giorno lavorativo"

    # A smaller chunker split the passage: the piece is wholly contained in it.
    assert passage_similarity(PASSAGE, piece) == 1.0
    # A short header contained in the passage is not.
    assert passage_similarity(PASSAGE, "La penale") < 0.2


def test_an_unrelated_passage_does_not_match() -> None:
    other = "Il fornitore garantisce assistenza tecnica dal lunedì al venerdì."

    assert passage_similarity(PASSAGE, other) == 0.0


def test_keywords_of_a_question_and_its_answer_point_at_the_passage() -> None:
    reference = "Qual è la penale per ritardo? L'1 per mille al giorno."

    assert keyword_overlap(reference, PASSAGE) > keyword_overlap(
        reference, "Assistenza tecnica dal lunedì al venerdì."
    )
    assert keyword_overlap("a e o", PASSAGE) == 0.0


def test_position_prefers_the_same_page_then_the_same_place() -> None:
    source = [Position("doc", page=12, relative=0.5)]

    assert positional_score(Position("doc", page=12, relative=0.9), source) == 1.0
    assert positional_score(Position("doc", page=14, relative=0.5), source) == 1 / 3
    assert positional_score(Position("other", page=12, relative=0.5), source) == 0.0
    no_pages = [Position("doc", page=None, relative=0.5)]
    assert positional_score(Position("doc", None, 0.6), no_pages) == pytest.approx(0.9)
    assert relative_position(3, 7) == 0.5
    assert relative_position(0, 1) == 0.5


def test_position_matches_the_large_chunk_that_contains_a_small_one() -> None:
    # Small chunk 90 of 100 lies inside large chunk 9 of 10, the last one.
    source = [Position("doc", None, relative_position(90, 100))]

    containing = positional_score(
        Position("doc", None, relative_position(9, 10)), source
    )
    previous = positional_score(Position("doc", None, relative_position(8, 10)), source)
    assert containing > previous


def test_signals_that_do_not_apply_are_left_out_of_the_mean() -> None:
    weights = {SEMANTIC: 0.5, LEXICAL: 0.3, POSITIONAL: 0.2}

    assert combine({SEMANTIC: 0.8, LEXICAL: 0.4, POSITIONAL: 1.0}, weights) == (
        pytest.approx(0.72)
    )
    # Without a source there is no position: semantic and lexical share the weight.
    assert combine({SEMANTIC: 0.8, LEXICAL: 0.4, POSITIONAL: None}, weights) == (
        pytest.approx(0.65)
    )
    assert combine({SEMANTIC: None, LEXICAL: None, POSITIONAL: None}, weights) == 0.0


def test_bands_and_preselection_follow_the_thresholds() -> None:
    assert band(0.8, DEFAULT_THRESHOLDS) == ConfidenceBand.HIGH
    assert band(0.5, DEFAULT_THRESHOLDS) == ConfidenceBand.MEDIUM
    assert band(0.1, DEFAULT_THRESHOLDS) == ConfidenceBand.LOW
    assert preselect(0.95, has_source=True, thresholds=DEFAULT_THRESHOLDS)
    assert not preselect(0.85, has_source=True, thresholds=DEFAULT_THRESHOLDS)
    # Never without a source, however close the words.
    assert not preselect(1.0, has_source=False, thresholds=DEFAULT_THRESHOLDS)
    assert set(DEFAULT_WEIGHTS) == {SEMANTIC, LEXICAL, POSITIONAL}


def test_cosine() -> None:
    assert cosine([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert cosine([0.0, 0.0], [1.0, 0.0]) == 0.0
