import type { ChunkingConfigurationCoverage } from "@/api/types";
import { Badge } from "@/components/ui/Badge";

import { coverageKind, coverageLabel } from "./coverage";

export function CoverageBadge({ coverage }: { coverage: ChunkingConfigurationCoverage | undefined }) {
  if (!coverage) {
    return <span className="text-xs text-ink-muted">—</span>;
  }
  const kind = coverageKind(coverage);
  const tone = kind === "ready" ? "good" : kind === "partial" ? "warn" : "neutral";
  return (
    <span className="inline-flex items-center gap-2">
      <Badge tone={tone}>{coverageLabel(kind)}</Badge>
      <span className="text-xs text-ink-muted">
        {coverage.ready}/{coverage.total}
        {coverage.failed ? ` · ${coverage.failed} failed` : ""}
      </span>
    </span>
  );
}
