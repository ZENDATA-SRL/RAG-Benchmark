import type { QuestionVariantOutcomeRead } from "@/api/types";

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
