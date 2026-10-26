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

/** Start of a hit text, short enough to compare variants side by side. */
export function excerpt(text: string | null, length = 160): string {
  if (!text) return "";
  return text.length <= length ? text : `${text.slice(0, length)}…`;
}
