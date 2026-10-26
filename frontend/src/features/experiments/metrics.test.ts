import { describe, expect, it } from "vitest";

import type { MetricResultRead } from "@/api/types";

import { findMetric, formatMetric, metricKeys, sampleSize } from "./metrics";

const METRIC: MetricResultRead = {
  key: "recall@5",
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
