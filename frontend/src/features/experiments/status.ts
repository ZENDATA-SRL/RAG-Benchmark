import type { RunRead } from "@/api/types";

export function runStatusTone(status: string): "good" | "bad" | "warn" | "neutral" {
  if (status === "succeeded") return "good";
  if (status === "failed") return "bad";
  if (status === "running" || status === "pending") return "warn";
  return "neutral";
}

export function isRunActive(run: Pick<RunRead, "status">): boolean {
  return run.status === "running" || run.status === "pending";
}
