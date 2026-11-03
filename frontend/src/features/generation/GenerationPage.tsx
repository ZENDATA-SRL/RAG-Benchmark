import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { configurationsApi, generationApi } from "@/api/resources";
import type { GeneratedKind, ProposalStatus } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { TableSkeleton } from "@/components/ui/Skeleton";
import { TableFrame } from "@/components/ui/TableFrame";
import { formatDate } from "@/lib/format";
import { queryKeys } from "@/lib/queryClient";

import { DISCARD_LABELS, END_REASON_LABELS, isActive, KIND_LABELS, reviewUrl } from "./generation";

const POLL_MS = 3000;
const KINDS: GeneratedKind[] = ["single", "multi", "cross"];
const STATUSES: ProposalStatus[] = ["pending", "accepted", "rejected"];

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-line bg-paper px-3 py-2">
      <p className="text-xs text-ink-muted">{label}</p>
      <p className="font-mono text-lg">{value}</p>
      {hint ? <p className="text-[11px] text-ink-muted">{hint}</p> : null}
    </div>
  );
}

/** A generation job: its progress by phase, what the checks refused, its units and queue. */
export function GenerationPage() {
  const { jobId = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [kind, setKind] = useState<GeneratedKind | "">("");
  const [status, setStatus] = useState<ProposalStatus | "">("pending");

  const job = useQuery({
    queryKey: queryKeys.generation(jobId),
    queryFn: () => generationApi.get(jobId),
    refetchInterval: (current) => (isActive(current.state.data) ? POLL_MS : false),
  });
  const active = isActive(job.data);
  const units = useQuery({
    queryKey: queryKeys.generationUnits(jobId),
    queryFn: () => generationApi.units(jobId),
    refetchInterval: active ? POLL_MS : false,
    meta: { silent: true },
  });
  const proposals = useQuery({
    queryKey: queryKeys.generationProposals(jobId),
    queryFn: () => generationApi.proposals(jobId),
    refetchInterval: active ? POLL_MS : false,
    meta: { silent: true },
  });
  const configurations = useQuery({
    queryKey: queryKeys.configurations,
    queryFn: configurationsApi.list,
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: queryKeys.generation(jobId) });
  const cancel = useMutation({ mutationFn: () => generationApi.cancel(jobId), onSuccess: refresh });
  const resume = useMutation({ mutationFn: () => generationApi.resume(jobId), onSuccess: refresh });

  const data = job.data;
  if (job.isLoading) return <TableSkeleton />;
  if (!data) return <EmptyState title="Job not found" body="It may have been removed." />;

  const progress = data.progress;
  const rows = proposals.data?.items ?? [];
  const shown = rows.filter(
    (row) => (!kind || row.kind === kind) && (!status || row.status === status),
  );
  const waiting = rows.find((row) => row.status === "pending" && (!kind || row.kind === kind));
  const configurationName =
    configurations.data?.items.find((item) => item.id === data.chunking_configuration_id)?.name ??
    "…";
  const unitsLeft = (units.data ?? []).some((unit) => unit.status !== "succeeded");
  const discards = Object.entries(progress.discards).filter(([, count]) => count > 0);

  return (
    <div>
      <p className="mb-2 text-sm">
        <Link
          to={`/qa-sets/${data.qa_set_id}?configuration=${data.chunking_configuration_id}`}
          className="text-rust hover:underline"
        >
          QA set
        </Link>
        <span className="text-ink-muted"> / generated questions</span>
      </p>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Generated questions from {configurationName}</h1>
          <p className="mt-1 text-xs text-ink-muted">
            Created {formatDate(data.created_at)} · {String(data.params.provider)}/
            {String(data.params.model)} · {String(data.params.per_document)} per document,{" "}
            {String(data.params.cross_document)} across documents · prompt v{data.prompt_version}
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
          ) : unitsLeft ? (
            <Button variant="secondary" onClick={() => resume.mutate()} disabled={resume.isPending}>
              Resume
            </Button>
          ) : null}
          <Button
            disabled={!waiting}
            onClick={() => waiting && navigate(reviewUrl(data.id, waiting.id, kind))}
            data-testid="start-review"
          >
            {waiting ? "Start review" : "Nothing to review"}
          </Button>
        </div>
      </div>
      {data.error ? <p className="mb-3 text-sm text-danger">{data.error}</p> : null}

      <div className="mb-4 grid gap-3 sm:grid-cols-4" data-testid="generation-progress">
        <Stat
          label="Per document"
          value={`${progress.document.produced}/${progress.document.target}`}
          hint={`${progress.document.succeeded}/${progress.document.units} units done${
            progress.document.failed ? `, ${progress.document.failed} failed` : ""
          }`}
        />
        <Stat
          label="Across documents"
          value={`${progress.cross.produced}/${progress.cross.target}`}
          hint={`${progress.cross.succeeded}/${progress.cross.units} units done · ${progress.combinations} combination(s)`}
        />
        <Stat
          label="Pending · accepted · rejected"
          value={`${progress.proposals.pending} · ${progress.proposals.accepted} · ${progress.proposals.rejected}`}
          hint={KINDS.map((item) => `${progress.proposals.by_kind[item] ?? 0} ${item}`).join(", ")}
        />
        <Stat
          label="Documents covered"
          value={`${progress.documents_covered}/${data.document_ids.length}`}
        />
      </div>
      {discards.length > 0 ? (
        <p className="mb-4 text-xs text-ink-muted" data-testid="generation-discards">
          Refused by the checks:{" "}
          {discards
            .map(([reason, count]) => `${DISCARD_LABELS[reason] ?? reason} ${count}`)
            .join(", ")}
        </p>
      ) : null}

      <div className="mb-3 flex flex-wrap gap-2 text-xs">
        {(["", ...STATUSES] as const).map((item) => (
          <button
            key={item || "all"}
            type="button"
            onClick={() => setStatus(item)}
            className={`rounded-full border px-3 py-1 ${status === item ? "border-rust text-rust" : "border-line"}`}
          >
            {item || "all"}
          </button>
        ))}
        <span className="mx-1 border-l border-line" />
        {(["", ...KINDS] as const).map((item) => (
          <button
            key={item || "any"}
            type="button"
            onClick={() => setKind(item)}
            className={`rounded-full border px-3 py-1 ${kind === item ? "border-rust text-rust" : "border-line"}`}
          >
            {item ? KIND_LABELS[item] : "any kind"}
          </button>
        ))}
      </div>

      <TableFrame>
        <table className="w-full text-left text-sm" data-testid="generation-queue">
          <thead className="border-b border-line bg-paper text-xs text-ink-muted">
            <tr>
              <th className="px-4 py-2 font-medium">Question</th>
              <th className="px-4 py-2 font-medium">Kind</th>
              <th className="px-4 py-2 font-medium">Documents</th>
              <th className="px-4 py-2 font-medium">Status</th>
              <th className="px-4 py-2 font-medium" />
            </tr>
          </thead>
          <tbody>
            {shown.map((row) => (
              <tr key={row.id} className="border-b border-line last:border-0">
                <td className="px-4 py-3">
                  {row.text}
                  <p className="text-xs text-ink-muted">{row.answer}</p>
                </td>
                <td className="px-4 py-3 text-xs">{KIND_LABELS[row.kind]}</td>
                <td className="px-4 py-3 text-xs">
                  {[...new Set(row.chunks.map((chunk) => chunk.filename))].join(", ")}
                </td>
                <td className="px-4 py-3">
                  <Badge
                    tone={
                      row.status === "accepted"
                        ? "good"
                        : row.status === "rejected"
                          ? "bad"
                          : "neutral"
                    }
                  >
                    {row.status}
                  </Badge>
                </td>
                <td className="px-4 py-3 text-right">
                  <Link to={reviewUrl(data.id, row.id, kind)} className="text-rust hover:underline">
                    {row.status === "pending" ? "Review" : "Open"}
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableFrame>

      <h2 className="mb-2 mt-6 text-sm font-semibold">Units</h2>
      <TableFrame>
        <table className="w-full text-left text-xs" data-testid="generation-units">
          <thead className="border-b border-line bg-paper text-ink-muted">
            <tr>
              <th className="px-4 py-2 font-medium">Phase</th>
              <th className="px-4 py-2 font-medium">Document</th>
              <th className="px-4 py-2 font-medium">Produced</th>
              <th className="px-4 py-2 font-medium">Status</th>
              <th className="px-4 py-2 font-medium">Ended</th>
              <th className="px-4 py-2 font-medium" />
            </tr>
          </thead>
          <tbody>
            {(units.data ?? []).map((unit) => (
              <tr key={unit.id} className="border-b border-line last:border-0">
                <td className="px-4 py-2">{unit.phase}</td>
                <td className="px-4 py-2">
                  {unit.filename ?? `batch ${unit.position + 1}`}
                  {unit.summary ? <p className="text-ink-muted">{unit.summary}</p> : null}
                </td>
                <td className="px-4 py-2 font-mono">
                  {unit.produced}/{unit.target}
                </td>
                <td className="px-4 py-2">
                  {unit.status}
                  {unit.error ? <p className="text-danger">{unit.error}</p> : null}
                </td>
                <td className="px-4 py-2">
                  {unit.end_reason ? (END_REASON_LABELS[unit.end_reason] ?? unit.end_reason) : ""}
                </td>
                <td className="px-4 py-2 text-right">
                  {unit.trace_url ? (
                    <a
                      href={unit.trace_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-rust hover:underline"
                    >
                      Trace
                    </a>
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
