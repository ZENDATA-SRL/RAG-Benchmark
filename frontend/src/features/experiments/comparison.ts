import type { ComparisonVariantRead, MetricResultRead } from "@/api/types";

import { findMetric } from "./metrics";

/** A column of the comparison: which metric, and which statistic of it is drawn. */
export interface ComparisonColumn {
  key: string;
  label: string;
  stat?: "mean" | "median" | "p95";
}

/** How a bar reads against the baseline: the direction of the metric already applied. */
export type Verdict = "better" | "worse" | "same";

/** One variant on one metric: the value, how it differs from the baseline and its sample. */
export interface Bar {
  variant: ComparisonVariantRead;
  metric: MetricResultRead | undefined;
  value: number | null;
  /** Points for a ratio, the relative change for an amount; empty for the baseline itself. */
  delta: number | null;
  verdict: Verdict | null;
  isBest: boolean;
  /** Fewer questions counted than the variant with the most: the value rests on another set. */
  smallerSample: boolean;
}

export interface MetricBars {
  column: ComparisonColumn;
  unit: "ratio" | "amount";
  lowerIsBetter: boolean;
  description: string;
  /** What the bars are measured against: 1 for a ratio, the largest value for an amount. */
  scaleMax: number;
  baselineValue: number | null;
  bars: Bar[];
}

// The ratios of the metric families; every other metric is an amount (a rank, a count, a time).
const RATIO_METRICS = [
  /^(chunk_)?recall@/,
  /^(chunk_)?precision@/,
  /^(chunk_)?hit_rate@/,
  /^chunk_sufficient_hit@/,
  /^chunk_ndcg@/,
  /^(chunk_)?mrr$/,
  /^(chunk_)?set_recall$/,
  /^(chunk_)?set_precision$/,
  /^duplicate_hit_rate$/,
  /^refusal_accuracy$/,
];

export function isRatio(key: string): boolean {
  return RATIO_METRICS.some((pattern) => pattern.test(key));
}

// Differences smaller than this are noise at the precision the values are shown with.
const RATIO_EPSILON = 0.005;
const AMOUNT_EPSILON = 0.01;

function valueOf(metric: MetricResultRead | undefined, column: ComparisonColumn): number | null {
  if (!metric) return null;
  const stat = column.stat ?? (metric.aggregation === "median" ? "median" : "mean");
  return metric[stat] ?? null;
}

function deltaOf(value: number, baseline: number, unit: "ratio" | "amount"): number | null {
  if (unit === "ratio") return value - baseline;
  return baseline === 0 ? null : (value - baseline) / Math.abs(baseline);
}

function verdictOf(delta: number, unit: "ratio" | "amount", lowerIsBetter: boolean): Verdict {
  if (Math.abs(delta) < (unit === "ratio" ? RATIO_EPSILON : AMOUNT_EPSILON)) return "same";
  return delta < 0 === lowerIsBetter ? "better" : "worse";
}

/**
 * The bars of one metric for the variants on screen, measured against the baseline.
 * The baseline is read from every variant, shown or not, so hiding a variant never moves
 * the reference the others are compared with.
 */
export function metricBars(
  variants: ComparisonVariantRead[],
  allVariants: ComparisonVariantRead[],
  column: ComparisonColumn,
  baselineId: string | null,
): MetricBars | null {
  const found = allVariants
    .map((variant) => findMetric(variant, column.key))
    .find((metric) => metric !== undefined);
  if (!found) return null;
  const unit = isRatio(column.key) ? "ratio" : "amount";
  const lowerIsBetter = found.direction === "lower_is_better";
  const baseline = allVariants.find((variant) => variant.variant_id === baselineId);
  const baselineValue = baseline ? valueOf(findMetric(baseline, column.key), column) : null;

  const readings = variants.map((variant) => {
    const metric = findMetric(variant, column.key);
    return { variant, metric, value: valueOf(metric, column) };
  });
  const values = readings.flatMap((reading) => (reading.value === null ? [] : [reading.value]));
  const best =
    values.length === 0 ? null : lowerIsBetter ? Math.min(...values) : Math.max(...values);
  const widest = Math.max(0, ...readings.map((reading) => reading.metric?.n_effective ?? 0));

  const bars = readings.map(({ variant, metric, value }): Bar => {
    const isBaseline = variant.variant_id === baselineId;
    const delta =
      value === null || baselineValue === null || isBaseline
        ? null
        : deltaOf(value, baselineValue, unit);
    return {
      variant,
      metric,
      value,
      delta,
      verdict: delta === null ? null : verdictOf(delta, unit, lowerIsBetter),
      isBest: value !== null && value === best && values.length > 1,
      smallerSample: metric !== undefined && metric.n_effective < widest,
    };
  });
  return {
    column,
    unit,
    lowerIsBetter,
    description: found.description,
    scaleMax: unit === "ratio" ? 1 : Math.max(1e-9, ...values, baselineValue ?? 0),
    baselineValue,
    bars,
  };
}

/** `+0.08` points for a ratio, `-12%` for an amount; the sign is always shown. */
export function formatDelta(delta: number, unit: "ratio" | "amount"): string {
  const sign = delta > 0 ? "+" : delta < 0 ? "−" : "±";
  const size = Math.abs(delta);
  return unit === "ratio" ? `${sign}${size.toFixed(2)}` : `${sign}${Math.round(size * 100)}%`;
}

export function formatValue(value: number | null, unit: "ratio" | "amount"): string {
  if (value === null) return "—";
  if (unit === "ratio") return value.toFixed(2);
  return Math.abs(value) >= 100 ? String(Math.round(value)) : value.toFixed(1);
}

/** What the summary says of one variant: how many comparable metrics it leads, and lacks. */
export interface WinCount {
  wins: number;
  /** The same for every variant: the metrics at least two of them have a value on. */
  of: number;
  /** Comparable metrics this variant has no value on, which it cannot lead. */
  missing: number;
}

/** A chart with a value on at least two variants: with one there is nothing to compare. */
function isComparable(chart: MetricBars): boolean {
  return chart.bars.filter((bar) => bar.value !== null).length > 1;
}

/** The metrics left out of the count, since a single variant has a value on them. */
export function notComparedLabels(charts: MetricBars[]): string[] {
  return charts.filter((chart) => !isComparable(chart)).map((chart) => chart.column.label);
}

/**
 * How many metrics each variant is the best on. Only metrics at least two variants have a
 * value on count, and the total is the same for all of them: a variant with fewer values
 * (no chunk-level evidence under its configuration, say) must not look better for having
 * fewer metrics to lose on.
 */
export function winCounts(charts: MetricBars[]): Map<string, WinCount> {
  const comparable = charts.filter(isComparable);
  const counts = new Map<string, WinCount>();
  for (const chart of comparable) {
    for (const bar of chart.bars) {
      const entry = counts.get(bar.variant.variant_id) ?? {
        wins: 0,
        of: comparable.length,
        missing: 0,
      };
      if (bar.value === null) entry.missing += 1;
      else if (bar.isBest) entry.wins += 1;
      counts.set(bar.variant.variant_id, entry);
    }
  }
  return counts;
}

/** The baseline to start from: the first variant marked as one, else the first variant. */
export function defaultBaseline(variants: ComparisonVariantRead[]): string | null {
  return (variants.find((variant) => variant.is_baseline) ?? variants[0])?.variant_id ?? null;
}

/** The labels of the corpus snapshots the variants were run on, without repeats. */
export function corpusSnapshotLabels(variants: ComparisonVariantRead[]): string[] {
  return [...new Set(variants.map((variant) => variant.corpus_snapshot.label))];
}
