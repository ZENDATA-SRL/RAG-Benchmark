import type { ExperimentType, RunRead } from "@/api/types";

/** How an experiment's type reads in the UI. */
export function experimentTypeLabel(type: ExperimentType): string {
  return type === "qa" ? "Q&A" : "retrieval";
}

export function runStatusTone(status: string): "good" | "bad" | "warn" | "neutral" {
  if (status === "succeeded") return "good";
  if (status === "failed") return "bad";
  if (status === "running" || status === "pending") return "warn";
  return "neutral";
}

export function isRunActive(run: Pick<RunRead, "status">): boolean {
  return run.status === "running" || run.status === "pending";
}

/** A re-evaluation runs on the worker after the run ended: the page polls until it closes. */
export function isEvaluating(run: Pick<RunRead, "progress">): boolean {
  return run.progress.evaluation?.status === "running";
}
