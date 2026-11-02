import { describe, expect, it } from "vitest";

import type { MetricResultRead } from "@/api/types";

import {
  callMetricKeys,
  chunkMetricKeys,
  describeCoverage,
  excludedDetail,
  findMetric,
  formatAnswerMetric,
  formatCeiling,
  formatMetric,
  metricGuide,
  metricKeys,
  sampleSize,
  setMetricKeys,
} from "./metrics";

const METRIC: MetricResultRead = {
  key: "recall@5",
  family: "retrieval",
  level: "document",
  direction: "higher_is_better",
  aggregation: "mean",
  description: "Share of the gold documents reached by the first 5 chunks.",
  mean: 0.7834,
  stddev: 0.1,
  median: 0.8,
  p95: 0.9,
  n_effective: 142,
  n_excluded: 11,
};

describe("metric formatting", () => {
  it("shows the value with effective out of asked questions", () => {
    expect(sampleSize(METRIC)).toBe("142/153");
    expect(formatMetric(METRIC)).toBe("0.78 (142/153)");
  });

  it("keeps the sample when there is no value", () => {
    expect(formatMetric({ ...METRIC, mean: null, n_effective: 0, n_excluded: 3 })).toBe("— (0/3)");
  });

  it("shows a dash for a missing metric", () => {
    expect(formatMetric(undefined)).toBe("—");
  });

  it("builds the columns of a cutoff and finds a metric by key", () => {
    expect(metricKeys(3)).toEqual([
      "recall@3",
      "precision@3",
      "hit_rate@3",
      "mrr",
      "first_relevant_rank",
    ]);
    expect(findMetric({ metrics: [METRIC] }, "recall@5")).toBe(METRIC);
    expect(findMetric({ metrics: [METRIC] }, "mrr")).toBeUndefined();
  });
});

describe("chunk-level results", () => {
  it("builds the chunk columns of a cutoff", () => {
    expect(chunkMetricKeys(5)).toEqual([
      "chunk_recall@5",
      "chunk_hit_rate@5",
      "chunk_sufficient_hit@5",
      "chunk_precision@5",
      "chunk_ndcg@5",
      "chunk_mrr",
    ]);
  });

  it("lists why questions were excluded, one reason per line", () => {
    expect(
      excludedDetail({
        n_excluded: 12,
        excluded_reasons: { evidence_not_reviewed: 3, evidence_not_found: 9 },
      }),
    ).toBe("evidence not found: 9\nevidence not reviewed: 3");
    expect(excludedDetail({ n_excluded: 0, excluded_reasons: {} })).toBe("No question excluded");
  });

  it("describes the evidence of a group and its recall ceiling", () => {
    expect(
      describeCoverage({
        answerable: 50,
        confirmed: 38,
        not_found: 9,
        to_review: 0,
        not_reviewed: 3,
      }),
    ).toBe("38 confirmed · 9 not found · 0 to review · 3 not reviewed");
    expect(describeCoverage(null)).toMatch(/re-evaluate/);
    expect(formatCeiling(0.8163)).toBe("0.82");
    expect(formatCeiling(null)).toBe("—");
  });
});

describe("Q&A columns", () => {
  it("keeps the set size and the repeated hits next to the set recall", () => {
    expect(setMetricKeys(true).slice(0, 3)).toEqual([
      "set_recall",
      "retrieved_set_size",
      "duplicate_hit_rate",
    ]);
  });

  it("drops the chunk-level columns when they do not compare", () => {
    expect(setMetricKeys(false).some((key) => key.startsWith("chunk_"))).toBe(false);
    expect(callMetricKeys(false)).not.toContain("chunk_first_relevant_call_index");
    expect(callMetricKeys(true)).toContain("chunk_first_relevant_call_index");
  });
});

describe("formatAnswerMetric", () => {
  const latency = {
    key: "answer_latency_ms",
    family: "efficiency",
    level: null,
    direction: "lower_is_better",
    aggregation: "mean",
    description: "Time to answer.",
    mean: 1500,
    stddev: 0,
    median: 1840.4,
    p95: null,
    n_effective: 48,
    n_excluded: 2,
    excluded_reasons: { execution_failed: 2 },
  } as const;

  it("shows the chosen statistic with its sample", () => {
    expect(formatAnswerMetric(latency, { stat: "median", unit: "amount" })).toBe("1840 (48/50)");
    expect(formatAnswerMetric(latency, { stat: "p95", unit: "amount" })).toBe("— (48/50)");
    expect(formatAnswerMetric(undefined, { stat: "mean", unit: "ratio" })).toBe("—");
  });
});

describe("metricGuide", () => {
  const rank = {
    ...METRIC,
    key: "first_relevant_rank",
    direction: "lower_is_better",
    aggregation: "median",
    description: "Rank of the first relevant chunk.",
  } satisfies MetricResultRead;

  it("explains each column with its direction and the statistic its cell reports", () => {
    const guide = metricGuide(
      [{ metrics: [METRIC, rank] }],
      [
        { key: "recall@5", label: "recall@5" },
        { key: "first_relevant_rank", label: "first_relevant_rank" },
        { key: "recall@5", label: "recall p95", stat: "p95" },
      ],
    );
    expect(guide.map((entry) => entry.reading)).toEqual([
      "higher is better · mean over questions",
      "lower is better · median over questions",
      "higher is better · 95th percentile over questions",
    ]);
    expect(guide[1].description).toBe("Rank of the first relevant chunk.");
  });

  it("leaves out a column no variant has a value for", () => {
    expect(metricGuide([{ metrics: [METRIC] }], [{ key: "mrr", label: "mrr" }])).toEqual([]);
  });
});
