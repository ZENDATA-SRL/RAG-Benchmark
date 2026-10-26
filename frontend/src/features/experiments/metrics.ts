import type {
  EvidenceCountsRead,
  MetricResultRead,
  ResultGroupRead,
  VariantResultRead,
} from "@/api/types";

export const CUTOFFS = [1, 3, 5, 10] as const;
export const DEFAULT_CUTOFF = 5;

/** Document-level columns of the results table for one cutoff, in display order. */
export function metricKeys(cutoff: number): string[] {
  return [
    `recall@${cutoff}`,
    `precision@${cutoff}`,
    `hit_rate@${cutoff}`,
    "mrr",
    "first_relevant_rank",
  ];
}

/** Chunk-level columns for one cutoff: they only compare within one chunking configuration. */
export function chunkMetricKeys(cutoff: number): string[] {
  return [
    `chunk_recall@${cutoff}`,
    `chunk_sufficient_hit@${cutoff}`,
    `chunk_precision@${cutoff}`,
    `chunk_ndcg@${cutoff}`,
    "chunk_mrr",
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

/** Why questions were left out, one reason per line, for the tooltip of a value. */
export function excludedDetail(
  metric: Pick<MetricResultRead, "n_excluded" | "excluded_reasons"> | undefined,
): string {
  if (!metric || metric.n_excluded === 0) return "No question excluded";
  const reasons = Object.entries(metric.excluded_reasons ?? {}).sort(([a], [b]) =>
    a.localeCompare(b),
  );
  if (reasons.length === 0) return `${metric.n_excluded} excluded`;
  return reasons.map(([reason, count]) => `${reason.replaceAll("_", " ")}: ${count}`).join("\n");
}

/** The review state of a configuration's evidence, in one line. */
export function describeCoverage(coverage: EvidenceCountsRead | null | undefined): string {
  if (!coverage) return "evidence not recorded: re-evaluate the run";
  return [
    `${coverage.confirmed} confirmed`,
    `${coverage.not_found} not found`,
    `${coverage.to_review} to review`,
    `${coverage.not_reviewed} not reviewed`,
  ].join(" · ");
}

export function formatCeiling(ceiling: number | null | undefined): string {
  return ceiling === null || ceiling === undefined ? "—" : ceiling.toFixed(2);
}

/** The groups the selected variants come from: more than one means chunk metrics do not compare. */
export function groupsOf(groups: ResultGroupRead[], variantIds: Iterable<string>): string[] {
  const wanted = new Set(variantIds);
  return groups
    .filter((group) => group.variants.some((variant) => wanted.has(variant.variant_id)))
    .map((group) => group.chunking_configuration_id);
}

/** Every variant of the run, in group order. */
export function allVariants(groups: ResultGroupRead[]): VariantResultRead[] {
  return groups.flatMap((group) => group.variants);
}
