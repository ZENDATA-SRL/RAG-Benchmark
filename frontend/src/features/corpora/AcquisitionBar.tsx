import type { CorpusProgress } from "@/api/types";
import { ProgressBar } from "@/components/ui/ProgressBar";

const STORED = "stored";

export function AcquisitionBar({ progress }: { progress: CorpusProgress }) {
  const stored = progress.by_status?.[STORED] ?? 0;
  const failed = progress.by_status?.failed ?? 0;
  return (
    <div>
      <ProgressBar value={stored} max={progress.total || 1} label="Acquisition (stored documents)" />
      <p className="mt-1 text-xs text-ink-muted">
        {stored} stored
        {failed ? ` · ${failed} failed` : ""}
        {progress.total ? ` of ${progress.total}` : " · empty corpus"}
      </p>
    </div>
  );
}
