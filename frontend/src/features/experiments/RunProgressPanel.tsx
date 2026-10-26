import type { RunRead } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ProgressBar } from "@/components/ui/ProgressBar";

import { isRunActive, runStatusTone } from "./status";

function Counter({ label, value, hint }: { label: string; value: number; hint: string }) {
  return (
    <div className="rounded-md bg-paper px-3 py-2" data-testid={`progress-${label}`}>
      <dt className="text-xs text-ink-muted">{label}</dt>
      <dd className="font-mono text-lg">{value}</dd>
      <p className="text-[11px] text-ink-muted">{hint}</p>
    </div>
  );
}

/** Same layout as the materialisation panel, with the counters of an experiment run. */
export function RunProgressPanel({
  run,
  onCancel,
  onResume,
  busy,
}: {
  run: Pick<RunRead, "status" | "progress" | "error">;
  onCancel?: () => void;
  onResume?: () => void;
  busy?: boolean;
}) {
  const { total, succeeded, failed, pending } = run.progress;
  const active = isRunActive(run);

  return (
    <section
      className="rounded-xl border border-line bg-paper-raised p-4"
      data-testid="progress-panel"
    >
      <header className="mb-3 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold">Run</h2>
          <p className="text-xs text-ink-muted">
            One execution is one question asked to one variant, once per repetition. Resuming runs
            only what is not done yet.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge tone={runStatusTone(run.status)}>{run.status}</Badge>
          {active && onCancel ? (
            <Button variant="secondary" onClick={onCancel} disabled={busy}>
              Cancel
            </Button>
          ) : null}
          {!active && pending + failed > 0 && onResume ? (
            <Button variant="secondary" onClick={onResume} disabled={busy}>
              Resume
            </Button>
          ) : null}
        </div>
      </header>
      <ProgressBar value={succeeded + failed} max={total || 1} label="Executions" />
      <dl className="mt-3 grid grid-cols-2 gap-2 text-sm sm:grid-cols-3">
        <Counter label="succeeded" value={succeeded} hint="retrieval answered" />
        <Counter label="failed" value={failed} hint="the run goes on without them" />
        <Counter label="pending" value={pending} hint="still to do" />
      </dl>
      {run.error ? <p className="mt-3 text-sm text-danger">{run.error}</p> : null}
    </section>
  );
}
