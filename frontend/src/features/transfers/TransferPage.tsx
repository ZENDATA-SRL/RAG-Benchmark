import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { configurationsApi, transfersApi } from "@/api/resources";
import type { QueueState, TransferRead } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { TableSkeleton } from "@/components/ui/Skeleton";
import { TableFrame } from "@/components/ui/TableFrame";
import { formatDate } from "@/lib/format";
import { queryKeys } from "@/lib/queryClient";

import { formatScore, QUEUE_STATES, queueLabel, queueTone, reviewUrl } from "./queue";

const POLL_MS = 2000;

function isActive(job: TransferRead | undefined): boolean {
  return !job || job.status === "pending" || job.status === "running";
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-line bg-paper px-3 py-2">
      <p className="text-xs text-ink-muted">{label}</p>
      <p className="font-mono text-lg">{value}</p>
      {hint ? <p className="text-[11px] text-ink-muted">{hint}</p> : null}
    </div>
  );
}

/** A proposal or transfer job: its progress, its recall ceiling and its review queue. */
export function TransferPage() {
  const { transferId = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [state, setState] = useState<QueueState | "">("");

  const job = useQuery({
    queryKey: queryKeys.transfer(transferId),
    queryFn: () => transfersApi.get(transferId),
    refetchInterval: (current) => (isActive(current.state.data) ? POLL_MS : false),
  });
  const active = isActive(job.data);
  const queue = useQuery({
    queryKey: queryKeys.transferQueue(transferId, ""),
    queryFn: () => transfersApi.questions(transferId),
    refetchInterval: active ? POLL_MS : false,
    meta: { silent: true },
  });
  const configurations = useQuery({
    queryKey: queryKeys.configurations,
    queryFn: configurationsApi.list,
  });
  const names = new Map((configurations.data?.items ?? []).map((item) => [item.id, item.name]));

  const refresh = () => queryClient.invalidateQueries({ queryKey: queryKeys.transfer(transferId) });
  const cancel = useMutation({
    mutationFn: () => transfersApi.cancel(transferId),
    onSuccess: refresh,
  });
  const resume = useMutation({
    mutationFn: () => transfersApi.resume(transferId),
    onSuccess: refresh,
  });

  const data = job.data;
  const rows = queue.data?.items ?? [];
  const counts = new Map<QueueState, number>();
  for (const row of rows) counts.set(row.state, (counts.get(row.state) ?? 0) + 1);
  const shown = state ? rows.filter((row) => row.state === state) : rows;
  const waiting = rows.find((row) =>
    (["preselected", "to_review", "no_candidates"] as QueueState[]).includes(row.state),
  );
  const url = (questionId: string) =>
    data ? reviewUrl(data.qa_set_id, questionId, data.id, data.target_configuration_id) : "#";

  if (job.isLoading) return <TableSkeleton />;
  if (!data) return <EmptyState title="Job not found" body="It may have been removed." />;
  const progress = data.progress;

  return (
    <div>
      <p className="mb-2 text-sm">
        <Link
          to={`/qa-sets/${data.qa_set_id}?configuration=${data.target_configuration_id}`}
          className="text-rust hover:underline"
        >
          QA set
        </Link>
        <span className="text-ink-muted"> / suggested chunks</span>
      </p>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">
            {data.source_configuration_id
              ? `Transfer ${names.get(data.source_configuration_id) ?? "…"} → ${names.get(data.target_configuration_id) ?? "…"}`
              : `Suggested chunks under ${names.get(data.target_configuration_id) ?? "…"}`}
          </h1>
          <p className="mt-1 text-xs text-ink-muted">
            Created {formatDate(data.created_at)} · weights{" "}
            {Object.entries(data.signal_weights)
              .map(([name, value]) => `${name} ${value}`)
              .join(", ")}{" "}
            · bands high ≥ {data.confidence_thresholds.high}, low &lt;{" "}
            {data.confidence_thresholds.low}
            {data.source_configuration_id
              ? ` · pre-selected from lexical ${data.confidence_thresholds.preselect}`
              : " · nothing pre-selected without a source"}
            {data.embedding_profile_id ? "" : " · no embedder: words only"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge tone={data.status === "failed" ? "bad" : active ? "info" : "neutral"}>
            {data.status}
          </Badge>
          {active ? (
            <Button variant="secondary" onClick={() => cancel.mutate()} disabled={cancel.isPending}>
              Cancel
            </Button>
          ) : progress.ranked < progress.total ? (
            <Button variant="secondary" onClick={() => resume.mutate()} disabled={resume.isPending}>
              Resume
            </Button>
          ) : null}
          <Button
            disabled={!waiting}
            onClick={() => waiting && navigate(url(waiting.question_id))}
            data-testid="start-review"
          >
            {waiting ? "Start review" : "Nothing to review"}
          </Button>
        </div>
      </div>
      {data.error ? <p className="mb-3 text-sm text-danger">{data.error}</p> : null}

      <div className="mb-4 grid gap-3 sm:grid-cols-4" data-testid="transfer-progress">
        <Stat
          label="Ranked"
          value={`${progress.ranked}/${progress.total}`}
          hint={progress.failed ? `${progress.failed} failed` : undefined}
        />
        <Stat label="Reviewed" value={`${progress.reviewed}/${progress.total}`} />
        <Stat
          label="Confirmed · not found"
          value={`${progress.confirmed} · ${progress.not_found}`}
        />
        <Stat
          label="Recall ceiling"
          value={formatScore(data.recall_ceiling)}
          hint="share of the reviewed questions whose evidence exists here"
        />
      </div>

      <div className="mb-3 flex flex-wrap gap-2 text-xs">
        <button
          type="button"
          onClick={() => setState("")}
          className={`rounded-full border px-3 py-1 ${state === "" ? "border-rust text-rust" : "border-line"}`}
        >
          All {rows.length}
        </button>
        {QUEUE_STATES.filter((item) => counts.get(item)).map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => setState(item)}
            className={`rounded-full border px-3 py-1 ${state === item ? "border-rust text-rust" : "border-line"}`}
          >
            {queueLabel(item)} {counts.get(item)}
          </button>
        ))}
      </div>

      <TableFrame>
        <table className="w-full text-left text-sm" data-testid="transfer-queue">
          <thead className="border-b border-line bg-paper text-xs text-ink-muted">
            <tr>
              <th className="px-4 py-2 font-medium">Question</th>
              <th className="px-4 py-2 font-medium">State</th>
              <th className="px-4 py-2 font-medium">Best score</th>
              <th className="px-4 py-2 font-medium">Plausible</th>
              <th className="px-4 py-2 font-medium" />
            </tr>
          </thead>
          <tbody>
            {shown.map((row) => (
              <tr key={row.question_id} className="border-b border-line last:border-0">
                <td className="px-4 py-3">
                  {row.text}
                  {row.error ? <p className="text-xs text-danger">{row.error}</p> : null}
                </td>
                <td className="px-4 py-3">
                  <Badge tone={queueTone(row.state)} className="whitespace-nowrap">
                    {queueLabel(row.state)}
                  </Badge>
                </td>
                <td className="px-4 py-3 font-mono text-xs">{formatScore(row.top_score)}</td>
                <td className="px-4 py-3 font-mono text-xs">
                  {row.plausible}
                  {row.preselected ? ` (${row.preselected} ticked)` : ""}
                </td>
                <td className="px-4 py-3 text-right">
                  {row.state !== "pending" ? (
                    <Link to={url(row.question_id)} className="text-rust hover:underline">
                      {row.state === "decided" ? "Open" : "Review"}
                    </Link>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableFrame>
    </div>
  );
}
