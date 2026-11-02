import { describe, expect, it } from "vitest";

import type { MetricResultRead, ResultGroupRead, VariantResultRead } from "@/api/types";

import {
  callMetricKeys,
  chunkMetricKeys,
  describeCoverage,
  excludedDetail,
  findMetric,
  formatAnswerMetric,
  formatCeiling,
  formatMetric,
  groupsOf,
  metricKeys,
  sampleSize,
  setMetricKeys,
} from "./metrics";

const METRIC: MetricResultRead = {
  key: "recall@5",
  family: "retrieval",
  level: "document",
  direction: "higher_is_better",
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
  const variant = (id: string): VariantResultRead => ({
    variant_id: id,
    name: id,
    is_baseline: false,
    index_build_id: "build",
    retrieval_profile_id: "profile",
    top_k: 5,
    metrics: [],
  });
  const group = (id: string, variants: string[]): ResultGroupRead => ({
    chunking_configuration_id: id,
    chunking_configuration_name: id,
    parsing: "pypdf",
    chunking: "recursive",
    variants: variants.map(variant),
  });

  it("builds the chunk columns of a cutoff", () => {
    expect(chunkMetricKeys(5)).toEqual([
      "chunk_recall@5",
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

  it("tells when selected variants span chunking configurations", () => {
    const groups = [group("small", ["a", "b"]), group("large", ["c"])];

    expect(groupsOf(groups, ["a", "b"])).toEqual(["small"]);
    expect(groupsOf(groups, ["a", "c"])).toEqual(["small", "large"]);
    expect(groupsOf(groups, [])).toEqual([]);
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
