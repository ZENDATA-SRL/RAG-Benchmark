from __future__ import annotations

import dataclasses
import math
import statistics
import uuid
from collections.abc import Collection, Mapping, Sequence

from src.infrastructure.database.enums import MetricLevel

# Cutoffs of the ranked metrics, counted in retrieved chunks: `@5` judges the first five
# chunks, which is what a generator would be given. Fixed and not taken from the retrieval
# profile's top-k, so that `recall@5` means the same thing in every variant and variants
# with different top-k stay comparable on one metric.
CUTOFFS = (1, 3, 5, 10)

MRR = "mrr"
FIRST_RELEVANT_RANK = "first_relevant_rank"
CHUNK_MRR = "chunk_mrr"
CHUNK_FIRST_RELEVANT_RANK = "chunk_first_relevant_rank"

# Gain of a gold chunk in nDCG when the annotator gave no graded relevance: a chunk that
# answers alone is worth twice one that only helps.
SUFFICIENT_GAIN = 2.0
SUPPORTING_GAIN = 1.0


@dataclasses.dataclass(frozen=True)
class MetricSpec:
    """The definition seeded for one metric key."""

    key: str
    direction: str
    aggregation: str
    description: str
    level: MetricLevel = MetricLevel.DOCUMENT


def metric_specs() -> list[MetricSpec]:
    """Every retrieval metric, document level first, in display order."""
    return document_metric_specs() + chunk_metric_specs()


def document_metric_specs() -> list[MetricSpec]:
    """The metrics that judge a retrieved chunk by the document it comes from."""
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


def chunk_metric_specs() -> list[MetricSpec]:
    """The metrics that judge a retrieved chunk against the confirmed evidence chunks.

    They only mean something within one chunking configuration, because the evidence is
    confirmed on the chunks that configuration produced.
    """
    chunk = MetricLevel.CHUNK
    specs = []
    for cutoff in CUTOFFS:
        specs.append(
            MetricSpec(
                f"chunk_recall@{cutoff}",
                "higher_is_better",
                "mean",
                f"Share of the evidence chunks among the first {cutoff} retrieved chunks.",
                chunk,
            )
        )
    for cutoff in CUTOFFS:
        specs.append(
            MetricSpec(
                f"chunk_precision@{cutoff}",
                "higher_is_better",
                "mean",
                f"Share of the first {cutoff} retrieved chunks that are evidence chunks; "
                "a query that retrieves fewer chunks is judged on those it retrieved.",
                chunk,
            )
        )
    for cutoff in CUTOFFS:
        specs.append(
            MetricSpec(
                f"chunk_hit_rate@{cutoff}",
                "higher_is_better",
                "mean",
                f"1 if any of the first {cutoff} retrieved chunks is an evidence chunk.",
                chunk,
            )
        )
    for cutoff in CUTOFFS:
        specs.append(
            MetricSpec(
                f"chunk_sufficient_hit@{cutoff}",
                "higher_is_better",
                "mean",
                f"1 if the first {cutoff} retrieved chunks are enough to answer: a "
                "sufficient chunk, or every supporting chunk when none is sufficient.",
                chunk,
            )
        )
    for cutoff in CUTOFFS:
        specs.append(
            MetricSpec(
                f"chunk_ndcg@{cutoff}",
                "higher_is_better",
                "mean",
                f"Normalised discounted cumulative gain of the first {cutoff} retrieved "
                "chunks, with the graded relevance of the evidence chunks as gain.",
                chunk,
            )
        )
    specs.append(
        MetricSpec(
            CHUNK_MRR,
            "higher_is_better",
            "mean",
            "Reciprocal of the rank of the first evidence chunk, 0 if none was retrieved.",
            chunk,
        )
    )
    specs.append(
        MetricSpec(
            CHUNK_FIRST_RELEVANT_RANK,
            "lower_is_better",
            "median",
            "Rank of the first evidence chunk; empty when none was retrieved.",
            chunk,
        )
    )
    return specs


@dataclasses.dataclass(frozen=True)
class GoldChunk:
    """A confirmed evidence chunk: whether it answers alone, and its gain in nDCG."""

    sufficient: bool
    gain: float


def gold_chunk(relevance: str, graded_relevance: int | None) -> GoldChunk:
    """The gold of an evidence chunk; the grade defaults to the kind of evidence."""
    sufficient = relevance == "sufficient"
    if graded_relevance is not None:
        gain = float(graded_relevance)
    else:
        gain = SUFFICIENT_GAIN if sufficient else SUPPORTING_GAIN
    return GoldChunk(sufficient=sufficient, gain=gain)


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


def chunk_metrics(
    ranked_chunks: Sequence[uuid.UUID | None], gold: Mapping[uuid.UUID, GoldChunk]
) -> dict[str, float | None]:
    """Chunk-level retrieval metrics of one query against its confirmed evidence chunks.

    A chunk retrieved more than once, by several calls of the same execution, keeps its
    first position and counts once: the second copy brings nothing new. Recall, precision,
    hit rate and the rank count every evidence chunk, sufficient or supporting. The
    sufficient hit asks whether the context was enough to answer: one sufficient chunk
    is, and when the annotator found none, it takes every supporting chunk together.

    Args:
        ranked_chunks: Chunk of each hit, best first; `None` for a chunk no longer known.
        gold: Evidence chunks of the question under the variant's configuration; must not
            be empty.

    Returns:
        A value per chunk metric key. `chunk_first_relevant_rank` is `None` when no
        evidence chunk was retrieved, and `chunk_ndcg@k` is `None` when every evidence
        chunk has a zero gain, since there is then nothing to normalise by.
    """
    ranked: list[uuid.UUID | None] = []
    seen: set[uuid.UUID] = set()
    for chunk_id in ranked_chunks:
        if chunk_id is not None:
            if chunk_id in seen:
                continue
            seen.add(chunk_id)
        ranked.append(chunk_id)

    sufficient = {chunk_id for chunk_id, item in gold.items() if item.sufficient}
    first = next(
        (index + 1 for index, chunk_id in enumerate(ranked) if chunk_id in gold), None
    )
    ideal = sorted((item.gain for item in gold.values()), reverse=True)

    scores: dict[str, float | None] = {}
    for cutoff in CUTOFFS:
        top = ranked[:cutoff]
        found = {chunk_id for chunk_id in top if chunk_id in gold}
        enough = bool(found & sufficient) if sufficient else found == set(gold)
        dcg = sum(
            gold[chunk_id].gain / math.log2(index + 2)
            for index, chunk_id in enumerate(top)
            if chunk_id in gold
        )
        idcg = sum(
            gain / math.log2(index + 2) for index, gain in enumerate(ideal[:cutoff])
        )
        scores[f"chunk_recall@{cutoff}"] = len(found) / len(gold)
        scores[f"chunk_precision@{cutoff}"] = len(found) / len(top) if top else 0.0
        scores[f"chunk_hit_rate@{cutoff}"] = 1.0 if found else 0.0
        scores[f"chunk_sufficient_hit@{cutoff}"] = 1.0 if enough else 0.0
        scores[f"chunk_ndcg@{cutoff}"] = dcg / idcg if idcg > 0 else None
    scores[CHUNK_MRR] = 1.0 / first if first else 0.0
    scores[CHUNK_FIRST_RELEVANT_RANK] = float(first) if first else None
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
