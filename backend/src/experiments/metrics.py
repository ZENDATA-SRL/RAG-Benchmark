from __future__ import annotations

import dataclasses
import math
import statistics
import uuid
from collections.abc import Collection, Sequence

# Cutoffs of the ranked metrics, counted in retrieved chunks: `@5` judges the first five
# chunks, which is what a generator would be given. Fixed and not taken from the retrieval
# profile's top-k, so that `recall@5` means the same thing in every variant and variants
# with different top-k stay comparable on one metric.
CUTOFFS = (1, 3, 5, 10)

MRR = "mrr"
FIRST_RELEVANT_RANK = "first_relevant_rank"


@dataclasses.dataclass(frozen=True)
class MetricSpec:
    """The definition seeded for one metric key."""

    key: str
    direction: str
    aggregation: str
    description: str


def metric_specs() -> list[MetricSpec]:
    """Every document-level retrieval metric, in display order."""
    specs = []
    for cutoff in CUTOFFS:
        specs.append(
            MetricSpec(
                f"recall@{cutoff}",
                "higher_is_better",
                "mean",
                f"Share of the gold documents that at least one of the first {cutoff} "
                "retrieved chunks comes from.",
            )
        )
    for cutoff in CUTOFFS:
        specs.append(
            MetricSpec(
                f"precision@{cutoff}",
                "higher_is_better",
                "mean",
                f"Share of the first {cutoff} retrieved chunks that come from a gold "
                "document; a query that retrieves fewer chunks is judged on those it "
                "retrieved.",
            )
        )
    for cutoff in CUTOFFS:
        specs.append(
            MetricSpec(
                f"hit_rate@{cutoff}",
                "higher_is_better",
                "mean",
                f"1 if any of the first {cutoff} retrieved chunks comes from a gold "
                "document, else 0.",
            )
        )
    specs.append(
        MetricSpec(
            MRR,
            "higher_is_better",
            "mean",
            "Reciprocal of the rank of the first chunk from a gold document, 0 if none "
            "was retrieved.",
        )
    )
    specs.append(
        MetricSpec(
            FIRST_RELEVANT_RANK,
            "lower_is_better",
            "median",
            "Rank of the first chunk from a gold document; empty when none was "
            "retrieved.",
        )
    )
    return specs


def document_metrics(
    ranked_documents: Sequence[uuid.UUID | None], gold: Collection[uuid.UUID]
) -> dict[str, float | None]:
    """Document-level retrieval metrics of one query, cut on the ranked chunks.

    The cutoff is applied to the chunks first, because they are what a generator receives,
    and relevance is then judged by the document each chunk comes from. Recall counts each
    gold document once however many of its chunks were retrieved; precision is the share
    of the chunks that are useful context. A chunk with no known document still takes its
    place in the ranking and is not relevant.

    Args:
        ranked_documents: Document of each retrieved chunk, best first; repeats are fine.
        gold: Documents that contain the answer; must not be empty.

    Returns:
        A value per metric key. `first_relevant_rank` is `None` when no gold document was
        retrieved, which is different from a worst value and is left out of its statistics.
    """
    relevant = [document in gold for document in ranked_documents]
    first = next((index + 1 for index, hit in enumerate(relevant) if hit), None)

    scores: dict[str, float | None] = {}
    for cutoff in CUTOFFS:
        top = ranked_documents[:cutoff]
        found = {document for document in top if document in gold}
        useful = sum(relevant[:cutoff])
        scores[f"recall@{cutoff}"] = len(found) / len(gold)
        scores[f"precision@{cutoff}"] = useful / len(top) if top else 0.0
        scores[f"hit_rate@{cutoff}"] = 1.0 if found else 0.0
    scores[MRR] = 1.0 / first if first else 0.0
    scores[FIRST_RELEVANT_RANK] = float(first) if first else None
    return scores


@dataclasses.dataclass(frozen=True)
class Statistics:
    """Summary of the scores of one metric; empty when nothing was effective."""

    mean: float | None
    stddev: float | None
    median: float | None
    p95: float | None


def summarize(scores: Sequence[float]) -> Statistics:
    """Mean, sample standard deviation, median and nearest-rank 95th percentile.

    The standard deviation of a single score is 0 and not undefined: there is nothing to
    spread, and an empty cell would read as "not computed".
    """
    if not scores:
        return Statistics(None, None, None, None)
    ordered = sorted(scores)
    rank = max(math.ceil(0.95 * len(ordered)), 1)
    return Statistics(
        mean=statistics.fmean(ordered),
        stddev=statistics.stdev(ordered) if len(ordered) > 1 else 0.0,
        median=statistics.median(ordered),
        p95=ordered[rank - 1],
    )
