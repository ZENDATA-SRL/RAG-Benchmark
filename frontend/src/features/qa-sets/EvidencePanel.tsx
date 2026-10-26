import type { EvidenceStatus, RelevanceGrade } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { formatDate } from "@/lib/format";

import {
  blockedReason,
  statusLabel,
  statusTone,
  type DraftChunk,
  type EvidenceDecision,
} from "./evidence";

export function EvidenceStatusBadge({ status }: { status: EvidenceStatus }) {
  return (
    <Badge tone={statusTone(status)} className="whitespace-nowrap">
      {statusLabel(status)}
    </Badge>
  );
}

export function EvidencePanel({
  status,
  confirmedBy,
  confirmedAt,
  draft,
  dirty,
  annotator,
  onAnnotatorChange,
  onRelevance,
  onOpen,
  onSave,
  saving,
}: {
  status: EvidenceStatus;
  confirmedBy?: string | null;
  confirmedAt?: string | null;
  draft: DraftChunk[];
  dirty: boolean;
  annotator: string;
  onAnnotatorChange: (name: string) => void;
  onRelevance: (chunk: DraftChunk, relevance: RelevanceGrade | null) => void;
  onOpen: (chunk: DraftChunk) => void;
  onSave: (decision: EvidenceDecision) => void;
  saving: boolean;
}) {
  const decisions: {
    decision: EvidenceDecision;
    label: string;
    variant: "primary" | "secondary";
  }[] = [
    { decision: "confirmed", label: "Confirm", variant: "primary" },
    { decision: "not_found", label: "Not found", variant: "secondary" },
    { decision: "to_review", label: "Save draft", variant: "secondary" },
  ];
  const reasons = decisions
    .map(({ decision }) => blockedReason(decision, draft, annotator))
    .filter((reason): reason is string => reason !== null);

  return (
    <section className="flex min-h-0 flex-col" data-testid="evidence-panel">
      <div className="flex items-center justify-between gap-2 border-b border-line px-3 py-2">
        <h2 className="text-sm font-semibold">Evidence</h2>
        <div className="flex items-center gap-2">
          {dirty ? <Badge tone="info">unsaved</Badge> : null}
          <EvidenceStatusBadge status={status} />
        </div>
      </div>
      {confirmedBy && (status === "confirmed" || status === "not_found") ? (
        <p className="px-3 pt-2 text-xs text-ink-muted">
          Decided by {confirmedBy}
          {confirmedAt ? ` · ${formatDate(confirmedAt)}` : ""}
        </p>
      ) : null}

      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-2">
        {draft.length === 0 ? (
          <p className="text-sm text-ink-muted">
            No chunk picked. Mark chunks as sufficient (they answer alone) or supporting (they
            help), or record that the evidence is not in this configuration.
          </p>
        ) : (
          <ul className="space-y-2" data-testid="evidence-chunks">
            {draft.map((chunk) => (
              <li key={chunk.chunk_id} className="rounded-lg border border-line p-2 text-xs">
                <div className="mb-1 flex items-center justify-between gap-2">
                  <button
                    type="button"
                    className="truncate text-left font-mono text-rust hover:underline"
                    onClick={() => onOpen(chunk)}
                  >
                    {chunk.filename} #{chunk.ordinal}
                  </button>
                  <select
                    aria-label={`Relevance of chunk ${chunk.ordinal}`}
                    value={chunk.relevance}
                    onChange={(event) => onRelevance(chunk, event.target.value as RelevanceGrade)}
                    className="rounded border border-line bg-paper-raised px-1 py-0.5"
                  >
                    <option value="sufficient">sufficient</option>
                    <option value="supporting">supporting</option>
                  </select>
                  <Button
                    variant="ghost"
                    aria-label={`Remove chunk ${chunk.ordinal}`}
                    onClick={() => onRelevance(chunk, null)}
                  >
                    ×
                  </Button>
                </div>
                <p className="line-clamp-3 whitespace-pre-wrap text-ink-muted">{chunk.text}</p>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="space-y-2 border-t border-line px-3 py-3">
        <label className="block text-xs">
          <span className="mb-1 block text-ink-muted">Annotator</span>
          <input
            value={annotator}
            onChange={(event) => onAnnotatorChange(event.target.value)}
            placeholder="Your name"
            className="w-full rounded-md border border-line bg-paper-raised px-2 py-1 text-sm"
          />
        </label>
        <div className="flex flex-wrap gap-2">
          {decisions.map(({ decision, label, variant }) => (
            <Button
              key={decision}
              variant={variant}
              disabled={saving || blockedReason(decision, draft, annotator) !== null}
              onClick={() => onSave(decision)}
            >
              {label}
            </Button>
          ))}
        </div>
        {reasons.length > 0 ? (
          <p className="text-xs text-ink-muted" data-testid="evidence-hint">
            {reasons[0]}
          </p>
        ) : null}
      </div>
    </section>
  );
}
