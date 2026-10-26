import { describe, expect, it } from "vitest";

import type { MetricResultRead, ResultGroupRead, VariantResultRead } from "@/api/types";

import {
  chunkMetricKeys,
  describeCoverage,
  excludedDetail,
  findMetric,
  formatCeiling,
  formatMetric,
  groupsOf,
  metricKeys,
  sampleSize,
} from "./metrics";

const METRIC: MetricResultRead = {
  key: "recall@5",
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
