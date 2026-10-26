from __future__ import annotations

import math
import uuid

import pytest
from src.experiments.metrics import (
    CUTOFFS,
    chunk_metrics,
    document_metrics,
    gold_chunk,
    metric_specs,
    summarize,
)

A, B, C = (uuid.uuid4() for _ in range(3))
S1, S2, P1, P2, X, Y = (uuid.uuid4() for _ in range(6))
SUFFICIENT = gold_chunk("sufficient", None)
SUPPORTING = gold_chunk("supporting", None)


def test_first_gold_chunk_at_rank_two() -> None:
    scores = document_metrics([B, A, A, C], {A})

    assert scores["recall@1"] == 0.0
    assert scores["recall@3"] == 1.0
    assert scores["precision@1"] == 0.0
    # Two of the first three chunks come from A.
    assert scores["precision@3"] == pytest.approx(2 / 3)
    assert scores["hit_rate@1"] == 0.0
    assert scores["hit_rate@3"] == 1.0
    assert scores["mrr"] == 0.5
    assert scores["first_relevant_rank"] == 2.0


def test_the_cutoff_is_on_chunks_not_on_distinct_documents() -> None:
    # The first three chunks only reach A and C: B, the fourth chunk, is beyond @3 even
    # though it is only the third distinct document.
    scores = document_metrics([A, A, C, B], {A, B})

    assert scores["recall@1"] == 0.5
    assert scores["recall@3"] == 0.5
    assert scores["recall@5"] == 1.0
    assert scores["precision@1"] == 1.0
    assert scores["precision@3"] == pytest.approx(2 / 3)
    assert scores["precision@5"] == pytest.approx(3 / 4)
    assert scores["hit_rate@1"] == 1.0
    assert scores["mrr"] == 1.0
    assert scores["first_relevant_rank"] == 1.0


def test_a_gold_document_counts_once_in_the_recall() -> None:
    scores = document_metrics([A, A, A], {A, B})

    assert scores["recall@3"] == 0.5
    assert scores["precision@3"] == 1.0


def test_the_rank_is_the_rank_of_the_chunk() -> None:
    # Two chunks of B come first: the first gold chunk is third, not second.
    scores = document_metrics([B, B, A], {A})

    assert scores["first_relevant_rank"] == 3.0
    assert scores["mrr"] == pytest.approx(1 / 3)
    assert scores["hit_rate@1"] == 0.0


def test_a_chunk_without_a_document_takes_its_place_and_is_not_relevant() -> None:
    scores = document_metrics([None, A], {A})

    assert scores["hit_rate@1"] == 0.0
    assert scores["precision@3"] == 0.5
    assert scores["first_relevant_rank"] == 2.0


def test_no_relevant_hit_scores_zero_and_has_no_rank() -> None:
    scores = document_metrics([B, C], {A})

    assert all(scores[f"recall@{k}"] == 0.0 for k in CUTOFFS)
    assert all(scores[f"hit_rate@{k}"] == 0.0 for k in CUTOFFS)
    assert scores["precision@5"] == 0.0
    assert scores["mrr"] == 0.0
    assert scores["first_relevant_rank"] is None


def test_nothing_retrieved_scores_zero() -> None:
    scores = document_metrics([], {A})

    assert scores["recall@5"] == 0.0
    assert scores["precision@5"] == 0.0
    assert scores["mrr"] == 0.0
    assert scores["first_relevant_rank"] is None


def test_a_query_that_retrieves_fewer_chunks_than_k_is_judged_on_those() -> None:
    scores = document_metrics([A, B], {A})

    assert scores["precision@5"] == 0.5
    assert scores["recall@5"] == 1.0
    # Fewer chunks than every cutoff above one: the scores stop changing.
    assert scores["precision@3"] == scores["precision@10"]


def test_every_score_has_a_seeded_definition() -> None:
    keys = {spec.key for spec in metric_specs()}
    scored = set(document_metrics([A], {A})) | set(
        chunk_metrics([A], {A: gold_chunk("sufficient", None)})
    )

    assert scored == keys


def test_summary_of_the_hand_computed_case() -> None:
    # recall@3 of the three questions above: 1, 1, 0.
    stats = summarize([1.0, 1.0, 0.0])

    assert stats.mean == pytest.approx(2 / 3)
    assert stats.median == 1.0
    assert stats.p95 == 1.0
    assert stats.stddev == pytest.approx(0.5773502691896257)


def test_summary_of_one_score_has_no_spread_and_of_none_is_empty() -> None:
    assert summarize([0.4]).stddev == 0.0
    empty = summarize([])
    assert (empty.mean, empty.stddev, empty.median, empty.p95) == (
        None,
        None,
        None,
        None,
    )


def test_p95_is_the_nearest_rank() -> None:
    stats = summarize([float(value) for value in range(1, 21)])

    assert stats.p95 == 19.0


# -- chunk level ---------------------------------------------------------------------------


def test_one_sufficient_chunk_at_rank_two() -> None:
    scores = chunk_metrics([X, S1, Y], {S1: SUFFICIENT})

    assert scores["chunk_recall@1"] == 0.0
    assert scores["chunk_recall@3"] == 1.0
    assert scores["chunk_precision@3"] == pytest.approx(1 / 3)
    assert scores["chunk_hit_rate@1"] == 0.0
    assert scores["chunk_sufficient_hit@1"] == 0.0
    assert scores["chunk_sufficient_hit@3"] == 1.0
    assert scores["chunk_mrr"] == 0.5
    assert scores["chunk_first_relevant_rank"] == 2.0
    # One gold chunk of gain 2 at rank 2, against the same chunk at rank 1.
    assert scores["chunk_ndcg@3"] == pytest.approx(1 / math.log2(3))


def test_one_of_several_sufficient_chunks_is_enough() -> None:
    scores = chunk_metrics([S2, X], {S1: SUFFICIENT, S2: SUFFICIENT})

    assert scores["chunk_recall@3"] == 0.5
    assert scores["chunk_sufficient_hit@1"] == 1.0


def test_supporting_chunks_are_enough_only_together() -> None:
    scores = chunk_metrics([P1, X, P2], {P1: SUPPORTING, P2: SUPPORTING})

    assert scores["chunk_recall@1"] == 0.5
    assert scores["chunk_hit_rate@1"] == 1.0
    assert scores["chunk_sufficient_hit@1"] == 0.0
    assert scores["chunk_sufficient_hit@3"] == 1.0


def test_a_supporting_chunk_does_not_stand_for_a_sufficient_one() -> None:
    scores = chunk_metrics([P1, X, Y], {S1: SUFFICIENT, P1: SUPPORTING})

    assert scores["chunk_hit_rate@3"] == 1.0
    assert scores["chunk_sufficient_hit@3"] == 0.0


def test_no_evidence_chunk_retrieved_scores_zero_and_has_no_rank() -> None:
    for ranked in ([], [X, Y]):
        scores = chunk_metrics(ranked, {S1: SUFFICIENT})

        assert all(scores[f"chunk_recall@{k}"] == 0.0 for k in CUTOFFS)
        assert scores["chunk_precision@5"] == 0.0
        assert scores["chunk_sufficient_hit@10"] == 0.0
        assert scores["chunk_ndcg@10"] == 0.0
        assert scores["chunk_mrr"] == 0.0
        assert scores["chunk_first_relevant_rank"] is None


def test_a_chunk_retrieved_twice_counts_once_at_its_first_rank() -> None:
    # Without the repeat dropped P1 would be fourth and outside @3.
    scores = chunk_metrics([X, S1, S1, P1], {S1: SUFFICIENT, P1: SUPPORTING})

    assert scores["chunk_recall@3"] == 1.0
    assert scores["chunk_precision@3"] == pytest.approx(2 / 3)
    assert scores["chunk_first_relevant_rank"] == 2.0


def test_ndcg_uses_the_graded_relevance_when_given() -> None:
    gold = {A: gold_chunk("supporting", 3), B: gold_chunk("sufficient", 1)}

    scores = chunk_metrics([B, A], gold)

    dcg = 1 / math.log2(2) + 3 / math.log2(3)
    ideal = 3 / math.log2(2) + 1 / math.log2(3)
    assert scores["chunk_ndcg@3"] == pytest.approx(dcg / ideal)
    assert scores["chunk_ndcg@1"] == pytest.approx(1 / 3)


def test_ndcg_is_empty_when_every_evidence_chunk_has_no_gain() -> None:
    scores = chunk_metrics([A], {A: gold_chunk("supporting", 0)})

    assert scores["chunk_ndcg@5"] is None
    assert scores["chunk_recall@5"] == 1.0


def test_default_gains_follow_the_kind_of_evidence() -> None:
    assert (SUFFICIENT.sufficient, SUFFICIENT.gain) == (True, 2.0)
    assert (SUPPORTING.sufficient, SUPPORTING.gain) == (False, 1.0)
