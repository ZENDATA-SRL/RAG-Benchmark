import type { ChunkingConfigurationCoverage } from "@/api/types";

export type CoverageKind = "ready" | "partial" | "missing";

export function coverageKind(coverage: ChunkingConfigurationCoverage): CoverageKind {
  if (coverage.total > 0 && coverage.ready === coverage.total) {
    return "ready";
  }
  if (coverage.ready > 0 || coverage.failed > 0) {
    return "partial";
  }
  return "missing";
}

export function coverageLabel(kind: CoverageKind): string {
  if (kind === "ready") return "ready";
  if (kind === "partial") return "partial";
  return "not materialised";
}
