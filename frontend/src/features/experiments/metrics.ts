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

/** Chunk-level columns for one cutoff, scored on the evidence confirmed under each configuration. */
export function chunkMetricKeys(cutoff: number): string[] {
  return [
    `chunk_recall@${cutoff}`,
    `chunk_hit_rate@${cutoff}`,
    `chunk_sufficient_hit@${cutoff}`,
    `chunk_precision@${cutoff}`,
    `chunk_ndcg@${cutoff}`,
    "chunk_mrr",
  ];
}

/**
 * Columns of a Q&A run computed on the distinct chunks of the experiment's scope. The size of
 * the set and its share of repeated hits sit right after the set recall: ten searches of
 * five reach up to fifty chunks and beat a top-5 without being a better retriever.
 */
export function setMetricKeys(includeChunk: boolean): string[] {
  return [
    "set_recall",
    "retrieved_set_size",
    "duplicate_hit_rate",
    "set_precision",
    ...(includeChunk ? ["chunk_set_recall", "chunk_set_precision"] : []),
  ];
}

/** Columns of a Q&A run about its calls: how many, how many hits, when the first evidence came. */
export function callMetricKeys(includeChunk: boolean): string[] {
  return [
    "retrieval_call_count",
    "retrieved_hit_count",
    "first_relevant_call_index",
    ...(includeChunk ? ["chunk_first_relevant_call_index"] : []),
  ];
}

/**
 * A column of the answer section of a Q&A run: which metric, and which statistic of it.
 * Latency is read on its median and p95, since a mean hides the slow answers.
 */
export interface AnswerColumn {
  key: string;
  label: string;
  stat: "mean" | "median" | "p95";
  unit: "ratio" | "amount";
}

export function answerColumns(): AnswerColumn[] {
  return [
    { key: "refusal_accuracy", label: "refusal_accuracy", stat: "mean", unit: "ratio" },
    { key: "answer_latency_ms", label: "latency p50 (ms)", stat: "median", unit: "amount" },
    { key: "answer_latency_ms", label: "latency p95 (ms)", stat: "p95", unit: "amount" },
    { key: "model_latency_ms", label: "model p50 (ms)", stat: "median", unit: "amount" },
    { key: "input_tokens", label: "tokens in", stat: "mean", unit: "amount" },
    { key: "output_tokens", label: "tokens out", stat: "mean", unit: "amount" },
  ];
}

/** An answer value with its sample: `0.92 (48/50)`, or `1840 (50/50)` for times and tokens. */
export function formatAnswerMetric(
  metric: MetricResultRead | undefined,
  column: Pick<AnswerColumn, "stat" | "unit">,
): string {
  if (!metric) return "—";
  const value = metric[column.stat];
  const text =
    value === null || value === undefined
      ? "—"
      : column.unit === "ratio"
        ? value.toFixed(2)
        : String(Math.round(value));
  return `${text} (${sampleSize(metric)})`;
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

/** One line of the metric guide: a column of the results table and how to read it. */
export interface MetricGuideEntry {
  label: string;
  description: string;
  reading: string;
}

/**
 * The explanation of the columns on screen, from the description the API serves with each
 * metric, with whether higher or lower is better and the statistic the cell reports.
 * A column no variant has a value for is left out: there is nothing to read.
 */
export function metricGuide(
  variants: Pick<VariantResultRead, "metrics">[],
  columns: { key: string; label: string; stat?: "mean" | "median" | "p95" }[],
): MetricGuideEntry[] {
  const entries: MetricGuideEntry[] = [];
  for (const column of columns) {
    const metric = variants
      .map((variant) => findMetric(variant, column.key))
      .find((found) => found !== undefined);
    if (!metric) continue;
    const stat = column.stat ?? (metric.aggregation === "median" ? "median" : "mean");
    entries.push({
      label: column.label,
      description: metric.description,
      reading: `${metric.direction === "lower_is_better" ? "lower is better" : "higher is better"} · ${stat === "p95" ? "95th percentile" : stat} over questions`,
    });
  }
  return entries;
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

/** Every variant of the run, in group order. */
export function allVariants(groups: ResultGroupRead[]): VariantResultRead[] {
  return groups.flatMap((group) => group.variants);
}
