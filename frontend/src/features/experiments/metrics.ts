import type { MetricResultRead, VariantResultRead } from "@/api/types";

export const CUTOFFS = [1, 3, 5, 10] as const;
export const DEFAULT_CUTOFF = 5;

/** Columns of the results table for one cutoff, in display order. */
export function metricKeys(cutoff: number): string[] {
  return [
    `recall@${cutoff}`,
    `precision@${cutoff}`,
    `hit_rate@${cutoff}`,
    "mrr",
    "first_relevant_rank",
  ];
}

export function findMetric(
  variant: Pick<VariantResultRead, "metrics">,
  key: string,
): MetricResultRead | undefined {
  return variant.metrics.find((metric) => metric.key === key);
}

/** How many questions the value rests on, out of those the variant was asked. */
export function sampleSize(metric: Pick<MetricResultRead, "n_effective" | "n_excluded">): string {
  return `${metric.n_effective}/${metric.n_effective + metric.n_excluded}`;
}

/** A value is never shown without its sample: `0.78 (142/153)`. */
export function formatMetric(metric: MetricResultRead | undefined): string {
  if (!metric) {
    return "—";
  }
  const value = metric.mean === null ? "—" : metric.mean.toFixed(2);
  return `${value} (${sampleSize(metric)})`;
}
