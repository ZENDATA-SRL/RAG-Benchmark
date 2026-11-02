import { ApiError } from "@/lib/errors";

type Offending = { name?: unknown; index_build_id?: unknown };

/** Readable text for the experiment-specific validation codes; null for any other error. */
export function experimentErrorMessage(error: unknown): string | null {
  if (!(error instanceof ApiError)) {
    return null;
  }
  if (error.code === "variants_outside_snapshot") {
    const variants = Array.isArray(error.details.variants)
      ? (error.details.variants as Offending[])
      : [];
    const names = variants.map((item) => String(item.name ?? item.index_build_id ?? "?"));
    return `These variants search an index built on a different corpus snapshot: ${names.join(", ")}. Every variant must search the same documents.`;
  }
  if (error.code === "gold_coverage_choice_required") {
    return "Some questions have gold documents that are not in the corpus snapshot. Choose to exclude them from the metrics before creating the experiment.";
  }
  if (error.code === "multiple_baselines") {
    return "Only one variant can be the baseline.";
  }
  if (error.code === "answer_profile_required") {
    return "Every variant of a Q&A experiment needs an answer profile.";
  }
  if (error.code === "citations_not_supported") {
    const profiles = Array.isArray(error.details.answer_profiles)
      ? error.details.answer_profiles.map(String)
      : [];
    return `The cited scope needs answer systems that cite their sources; these do not: ${profiles.join(", ")}.`;
  }
  if (error.code === "answer_system_not_available") {
    return `An answer system cannot run now: ${String(error.details.reason ?? error.message)}. The worker checks the model credentials when it starts.`;
  }
  return null;
}
