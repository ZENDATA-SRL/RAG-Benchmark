from __future__ import annotations

import uuid

import pytest
from src.experiments.metrics import (
    CUTOFFS,
    document_metrics,
    metric_specs,
    summarize,
)

A, B, C = (uuid.uuid4() for _ in range(3))


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

    assert set(document_metrics([A], {A})) == keys


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
