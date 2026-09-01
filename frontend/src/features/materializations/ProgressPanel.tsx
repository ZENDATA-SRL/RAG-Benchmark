import { useMutation, useQuery } from "@tanstack/react-query";

import { materializationsApi } from "@/api/resources";
import type { DocumentRead, MaterializationDetail, MaterializationProgress } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { queryKeys } from "@/lib/queryClient";

const TERMINAL = new Set(["ready", "failed"]);

export function progressCounts(progress: MaterializationProgress) {
  return {
    ready: progress.ready,
    cached: progress.cached,
    failed: progress.failed,
    pending: progress.pending,
    done: progress.ready + progress.cached + progress.failed,
  };
}

export function ProgressPanel({
  runId,
  documents,
  onClose,
}: {
  runId: string;
  documents: DocumentRead[];
  onClose?: () => void;
}) {
  const byId = new Map(documents.map((document) => [document.id, document.filename]));
  const query = useQuery({
    queryKey: queryKeys.materialization(runId),
    queryFn: () => materializationsApi.get(runId),
    refetchInterval: (current) => {
      const status = current.state.data?.status;
      return status && TERMINAL.has(status) ? false : 2000;
    },
  });

  const cancel = useMutation({
    mutationFn: () => materializationsApi.cancel(runId),
  });

  const run = query.data;
  if (!run) {
    return (
      <section className="rounded-xl border border-line bg-paper-raised p-4 text-sm text-ink-muted">
        Loading run…
      </section>
    );
  }

  return <ProgressPanelView run={run} filenames={byId} onCancel={() => cancel.mutate()} cancelling={cancel.isPending} onClose={onClose} />;
}

export function ProgressPanelView({
  run,
  filenames,
  onCancel,
  cancelling,
  onClose,
}: {
  run: MaterializationDetail;
  filenames: Map<string, string>;
  onCancel?: () => void;
  cancelling?: boolean;
  onClose?: () => void;
}) {
  const counts = progressCounts(run.progress ?? { ready: 0, cached: 0, failed: 0, pending: 0 });
  const running = run.status === "running" || run.status === "pending";
  const failures = run.failures ?? [];

  return (
    <section className="rounded-xl border border-line bg-paper-raised p-4" data-testid="progress-panel">
      <header className="mb-3 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold">Materialisation</h2>
          <p className="text-xs text-ink-muted">cached is reuse — the document was not recalculated.</p>
        </div>
        <div className="flex items-center gap-2">
          <Badge tone={run.status === "ready" ? "good" : run.status === "failed" ? "bad" : "warn"}>
            {run.status}
          </Badge>
          {running && onCancel ? (
            <Button variant="secondary" onClick={onCancel} disabled={cancelling}>
              Cancel
            </Button>
          ) : null}
          {onClose ? (
            <Button variant="ghost" onClick={onClose}>
              Dismiss
            </Button>
          ) : null}
        </div>
      </header>
      <ProgressBar value={counts.done} max={run.document_count || 1} label="Documents" />
      <dl className="mt-3 grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
        <Counter label="ready" value={counts.ready} hint="newly computed" />
        <Counter label="cached" value={counts.cached} hint="reused, not recomputed" />
        <Counter label="failed" value={counts.failed} hint="permanent error" />
        <Counter label="pending" value={counts.pending} hint="still in the queue" />
      </dl>
      {failures.length > 0 ? (
        <ul className="mt-4 space-y-1 text-sm" data-testid="progress-failures">
          {failures.map((failure) => (
            <li key={failure.document_id} className="text-danger">
              {filenames.get(failure.document_id) ?? failure.document_id}: {failure.error ?? "failed"}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function Counter({ label, value, hint }: { label: string; value: number; hint: string }) {
  return (
    <div className="rounded-md bg-paper px-3 py-2" data-testid={`progress-${label}`}>
      <dt className="text-xs text-ink-muted">{label}</dt>
      <dd className="font-mono text-lg">{value}</dd>
      <p className="text-[11px] text-ink-muted">{hint}</p>
    </div>
  );
}
