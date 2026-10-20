import type { IndexBuildRead } from "@/api/types";

export function buildStatusTone(status: string): "good" | "bad" | "warn" | "neutral" {
  if (status === "ready") return "good";
  if (status === "failed") return "bad";
  if (status === "running") return "warn";
  return "neutral";
}

/** A build can be (re)started unless a run is already in progress. */
export function canStart(build: Pick<IndexBuildRead, "status">): boolean {
  return build.status !== "running";
}

/** Poll the list only while some build is still running. */
export function hasRunningBuild(builds: Pick<IndexBuildRead, "status">[]): boolean {
  return builds.some((build) => build.status === "running");
}
