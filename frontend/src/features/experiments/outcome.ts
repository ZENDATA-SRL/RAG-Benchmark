import type {
  ExecutionDetailRead,
  HitOccurrenceRead,
  QuestionVariantOutcomeRead,
} from "@/api/types";

/** Whether a recorded refusal was right: refusing is right exactly on unanswerable questions. */
export function refusalRight(
  refused: boolean | null | undefined,
  answerable: boolean,
): boolean | null {
  return refused == null ? null : refused === !answerable;
}

/**
 * What an answer cost, in one line: `gpt-4o-mini · 1834 → 112 tokens · 1.8 s (model 1.5 s)`.
 * Empty when the execution recorded no usage, as in a retrieval run.
 */
export function describeUsage(execution: Pick<ExecutionDetailRead, "usage" | "timings">): string {
  const usage = execution.usage ?? {};
  const timings = execution.timings ?? {};
  const parts: string[] = [];
  if (typeof usage.model === "string") parts.push(usage.model);
  if (typeof usage.input_tokens === "number" && typeof usage.output_tokens === "number") {
    parts.push(`${usage.input_tokens} → ${usage.output_tokens} tokens`);
  }
  if (parts.length === 0) return "";
  const seconds = (ms: unknown) => (typeof ms === "number" ? `${(ms / 1000).toFixed(1)} s` : null);
  const total = seconds(timings.total_ms);
  const model = seconds(timings.model_ms);
  if (total) parts.push(model ? `${total} (model ${model})` : total);
  return parts.join(" · ");
}

/** One cell of the questions table: where the first gold document ranked, or why there is none. */
export function describeOutcome(
  outcome:
    | (Pick<QuestionVariantOutcomeRead, "status"> &
        Partial<Pick<QuestionVariantOutcomeRead, "first_relevant_rank" | "excluded_reason">>)
    | undefined,
): string {
  if (!outcome) {
    return "—";
  }
  if (outcome.excluded_reason) {
    return `excluded: ${outcome.excluded_reason}`;
  }
  if (outcome.status === "failed") {
    return "failed";
  }
  if (outcome.status !== "succeeded") {
    return outcome.status;
  }
  return outcome.first_relevant_rank === null || outcome.first_relevant_rank === undefined
    ? "not found"
    : `rank ${outcome.first_relevant_rank}`;
}

/** The chunk-level side of a cell: where the first evidence chunk ranked, or why it does not count. */
export function describeChunkOutcome(
  outcome:
    | (Pick<QuestionVariantOutcomeRead, "status"> &
        Partial<
          Pick<QuestionVariantOutcomeRead, "chunk_first_relevant_rank" | "chunk_excluded_reason">
        >)
    | undefined,
): string {
  if (!outcome || outcome.status !== "succeeded") {
    return "—";
  }
  if (outcome.chunk_excluded_reason) {
    return outcome.chunk_excluded_reason.replaceAll("_", " ");
  }
  return outcome.chunk_first_relevant_rank === null ||
    outcome.chunk_first_relevant_rank === undefined
    ? "not found"
    : `rank ${outcome.chunk_first_relevant_rank}`;
}

/** Every time a chunk came back, as `×2 · call 1 rank 1, call 2 rank 3`; empty when once. */
export function describeOccurrences(
  occurrences: Pick<HitOccurrenceRead, "call_index" | "rank">[],
): string {
  if (occurrences.length < 2) return "";
  const where = occurrences
    .map((occurrence) => `call ${occurrence.call_index} rank ${occurrence.rank}`)
    .join(", ");
  return `×${occurrences.length} · ${where}`;
}

/** Start of a hit text, short enough to compare variants side by side. */
export function excerpt(text: string | null, length = 160): string {
  if (!text) return "";
  return text.length <= length ? text : `${text.slice(0, length)}…`;
}

/** The annotation page of a question under a configuration, opened on a document if given. */
export function annotationUrl(
  qaSetId: string,
  questionId: string,
  configurationId: string,
  documentId?: string,
): string {
  const params = new URLSearchParams({ configuration: configurationId });
  if (documentId) params.set("document", documentId);
  return `/qa-sets/${qaSetId}/questions/${questionId}/annotate?${params.toString()}`;
}
