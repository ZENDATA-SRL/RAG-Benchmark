import { describe, expect, it } from "vitest";

import type { ComparisonVariantRead, MetricResultRead } from "@/api/types";

import {
  defaultBaseline,
  formatDelta,
  isRatio,
  metricBars,
  notComparedLabels,
  winCounts,
  type ComparisonColumn,
} from "./comparison";

function metric(key: string, mean: number, overrides: Partial<MetricResultRead> = {}) {
  return {
    key,
    family: "retrieval",
    level: "document",
    direction: "higher_is_better",
    aggregation: "mean",
    description: `What ${key} measures.`,
    mean,
    stddev: 0,
    median: mean,
    p95: mean,
    n_effective: 50,
    n_excluded: 0,
    excluded_reasons: {},
    ...overrides,
  } satisfies MetricResultRead;
}

function variant(
  name: string,
  metrics: MetricResultRead[],
  isBaseline = false,
): ComparisonVariantRead {
  return {
    variant_id: name,
    name,
    is_baseline: isBaseline,
    index_build_id: "build",
    retrieval_profile_id: "profile",
    top_k: 5,
    metrics,
    experiment_id: "experiment",
    experiment_name: "experiment",
    run_id: "run",
    corpus_snapshot: { id: "cs", label: "v1" },
    chunking_configuration_id: "chunking",
    chunking_configuration_name: "pypdf + 300",
    recall_ceiling: null,
  };
}

const RECALL: ComparisonColumn = { key: "recall@5", label: "recall@5" };
const LATENCY: ComparisonColumn = { key: "answer_latency_ms", label: "p50", stat: "median" };

describe("metricBars", () => {
  const base = variant("base", [metric("recall@5", 0.6)], true);
  const better = variant("better", [metric("recall@5", 0.8)]);
  const worse = variant("worse", [metric("recall@5", 0.5)]);
  const all = [base, better, worse];

  it("measures every bar against the baseline, in points for a ratio", () => {
    const chart = metricBars(all, all, RECALL, "base");

    const [baseBar, betterBar, worseBar] = chart!.bars;
    expect(baseBar.delta).toBeNull();
    expect(betterBar.delta).toBeCloseTo(0.2);
    expect(betterBar.verdict).toBe("better");
    expect(worseBar.verdict).toBe("worse");
    expect(chart!.scaleMax).toBe(1);
    expect(chart!.baselineValue).toBe(0.6);
  });

  it("marks the best value, and no one when there is nothing to compare", () => {
    const chart = metricBars(all, all, RECALL, "base");
    expect(chart!.bars.map((bar) => bar.isBest)).toEqual([false, true, false]);

    const alone = metricBars([base], [base], RECALL, "base");
    expect(alone!.bars[0].isBest).toBe(false);
  });

  it("reads lower as better when the metric says so, and the change of an amount in %", () => {
    const slow = variant(
      "slow",
      [metric("answer_latency_ms", 2000, { direction: "lower_is_better" })],
      true,
    );
    const fast = variant("fast", [
      metric("answer_latency_ms", 1000, { direction: "lower_is_better" }),
    ]);
    const all2 = [slow, fast];

    const chart = metricBars(all2, all2, LATENCY, "slow");

    expect(chart!.unit).toBe("amount");
    expect(chart!.bars[1].delta).toBeCloseTo(-0.5);
    expect(chart!.bars[1].verdict).toBe("better");
    expect(chart!.bars[1].isBest).toBe(true);
    expect(chart!.scaleMax).toBe(2000);
  });

  it("calls a difference below the precision shown the same", () => {
    const close = variant("close", [metric("recall@5", 0.602)]);
    const chart = metricBars([base, close], [base, close], RECALL, "base");
    expect(chart!.bars[1].verdict).toBe("same");
  });

  it("flags a value that counts fewer questions than the largest sample", () => {
    const short = variant("short", [metric("recall@5", 0.7, { n_effective: 31, n_excluded: 19 })]);
    const chart = metricBars([base, short], [base, short], RECALL, "base");
    expect(chart!.bars.map((bar) => bar.smallerSample)).toEqual([false, true]);
  });

  it("keeps the baseline when it is hidden, and skips a metric nobody has", () => {
    const chart = metricBars([better], all, RECALL, "base");
    expect(chart!.baselineValue).toBe(0.6);
    expect(chart!.bars[0].delta).toBeCloseTo(0.2);
    expect(metricBars(all, all, { key: "mrr", label: "mrr" }, "base")).toBeNull();
  });
});

describe("helpers", () => {
  it("tells ratios from amounts", () => {
    for (const key of ["recall@5", "chunk_ndcg@5", "chunk_mrr", "set_recall", "refusal_accuracy"]) {
      expect(isRatio(key)).toBe(true);
    }
    for (const key of ["first_relevant_rank", "answer_latency_ms", "retrieved_set_size"]) {
      expect(isRatio(key)).toBe(false);
    }
  });

  it("signs a delta", () => {
    expect(formatDelta(0.08, "ratio")).toBe("+0.08");
    expect(formatDelta(-0.5, "amount")).toBe("−50%");
  });

  it("counts the metrics each variant leads, out of the same total for all", () => {
    const a = variant("a", [metric("recall@5", 0.9), metric("mrr", 0.5)]);
    const b = variant("b", [metric("recall@5", 0.7), metric("mrr", 0.8)]);
    const charts = [
      metricBars([a, b], [a, b], RECALL, "a")!,
      metricBars([a, b], [a, b], { key: "mrr", label: "mrr" }, "a")!,
    ];

    const counts = winCounts(charts);

    expect(counts.get("a")).toEqual({ wins: 1, of: 2, missing: 0 });
    expect(counts.get("b")).toEqual({ wins: 1, of: 2, missing: 0 });
  });

  it("does not let a variant without a value look better for having fewer metrics", () => {
    const full = variant("full", [metric("recall@5", 0.9), metric("chunk_mrr", 0.5)]);
    const other = variant("other", [metric("recall@5", 0.7), metric("chunk_mrr", 0.8)]);
    const bare = variant("bare", [metric("recall@5", 0.6)]);
    const all = [full, other, bare];
    const charts = [
      metricBars(all, all, RECALL, "full")!,
      metricBars(all, all, { key: "chunk_mrr", label: "chunk_mrr" }, "full")!,
    ];

    const counts = winCounts(charts);

    expect(counts.get("bare")).toEqual({ wins: 0, of: 2, missing: 1 });
    expect(counts.get("other")).toEqual({ wins: 1, of: 2, missing: 0 });
  });

  it("leaves out a metric only one variant has a value on", () => {
    const a = variant("a", [metric("recall@5", 0.9), metric("chunk_mrr", 0.5)]);
    const b = variant("b", [metric("recall@5", 0.7)]);
    const charts = [
      metricBars([a, b], [a, b], RECALL, "a")!,
      metricBars([a, b], [a, b], { key: "chunk_mrr", label: "chunk_mrr" }, "a")!,
    ];

    expect(winCounts(charts).get("a")).toEqual({ wins: 1, of: 1, missing: 0 });
    expect(notComparedLabels(charts)).toEqual(["chunk_mrr"]);
  });

  it("starts from the marked baseline, else the first variant", () => {
    expect(defaultBaseline([variant("x", []), variant("y", [], true)])).toBe("y");
    expect(defaultBaseline([variant("x", []), variant("y", [])])).toBe("x");
    expect(defaultBaseline([])).toBeNull();
  });
});
