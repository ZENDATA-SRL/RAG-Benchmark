import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { experimentsApi } from "@/api/resources";
import type {
  CallDetailRead,
  EvidenceStatus,
  HitDetailRead,
  VariantDrilldownRead,
} from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { EvidenceStatusBadge } from "@/features/qa-sets/EvidencePanel";
import { queryKeys } from "@/lib/queryClient";

import { annotationUrl, describeOccurrences, excerpt } from "./outcome";

/**
 * A distinct chunk of an execution. One retrieved by several calls says so with every call
 * and rank, since repeated hits are wasted calls; one cited and never retrieved has no rank.
 */
function Hit({ hit }: { hit: HitDetailRead }) {
  const repeated = describeOccurrences(hit.occurrences ?? []);
  return (
    <li
      className={`rounded-md border px-3 py-2 text-xs ${hit.retrieved ? "border-line bg-paper" : "border-dashed border-amber bg-paper"}`}
      data-testid="hit"
    >
      <div className="flex flex-wrap items-center gap-2">
        {hit.retrieved ? (
          <>
            <span className="font-mono">#{hit.rank}</span>
            <span className="font-mono text-ink-muted">
              {hit.score === null ? "—" : hit.score.toFixed(3)}
            </span>
          </>
        ) : (
          <Badge tone="warn">cited, never retrieved</Badge>
        )}
        {repeated ? (
          <span className="font-mono text-amber" data-testid="hit-repeated">
            {repeated}
          </span>
        ) : null}
        {hit.retrieved && hit.cited ? <Badge tone="info">cited</Badge> : null}
        {hit.relevant_document ? <Badge tone="good">gold document</Badge> : null}
        {hit.relevant_chunk ? (
          <Badge tone="good">{`evidence${hit.relevance ? ` · ${hit.relevance}` : ""}`}</Badge>
        ) : null}
      </div>
      <p className="mt-1 font-medium break-all">
        {hit.filename ?? "unknown file"}
        {hit.page ? ` · p. ${hit.page}` : ""}
      </p>
      <p className="mt-1 text-ink-muted">{excerpt(hit.text)}</p>
    </li>
  );
}

/** The calls of an execution in order, shown only when it searched more than once. */
function Calls({ calls }: { calls: CallDetailRead[] }) {
  if (calls.length < 2) return null;
  return (
    <ol className="mb-2 space-y-1 text-xs" data-testid="calls">
      {calls.map((call) => (
        <li key={call.call_index} className="flex gap-2">
          <span className="font-mono text-ink-muted">call {call.call_index}</span>
          <span className="min-w-0 flex-1 truncate" title={call.query_text}>
            {call.query_text}
          </span>
          <span className="font-mono whitespace-nowrap text-ink-muted">
            {call.hit_count} hits · {call.new_chunk_count} new
          </span>
        </li>
      ))}
    </ol>
  );
}

/** The evidence of the question under the variant's configuration, and what it missed. */
function VariantEvidence({
  variant,
  qaSetId,
  questionId,
}: {
  variant: VariantDrilldownRead;
  qaSetId: string;
  questionId: string;
}) {
  const missed = variant.gold_chunks.filter((chunk) => !chunk.retrieved);
  return (
    <div className="mb-2 space-y-1 text-xs" data-testid="variant-evidence">
      <div className="flex items-center gap-2">
        <span className="text-ink-muted">Evidence</span>
        <EvidenceStatusBadge status={variant.evidence_status as EvidenceStatus} />
        {variant.evidence_status !== "confirmed" ? (
          <Link
            to={annotationUrl(qaSetId, questionId, variant.chunking_configuration_id)}
            className="text-rust hover:underline"
          >
            Annotate
          </Link>
        ) : null}
      </div>
      {missed.length > 0 ? (
        <div data-testid="missed-chunks">
          <p className="text-ink-muted">Not retrieved</p>
          <ul className="space-y-1">
            {missed.map((chunk) => (
              <li key={chunk.chunk_id}>
                <Link
                  to={annotationUrl(
                    qaSetId,
                    questionId,
                    variant.chunking_configuration_id,
                    chunk.document_id,
                  )}
                  className="font-mono text-rust hover:underline"
                >
                  {chunk.filename} #{chunk.ordinal}
                </Link>{" "}
                <span className="text-ink-muted">{chunk.relevance}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

/** Side panel: each variant's hits next to each other, with the question's gold documents. */
export function QuestionDrilldown({
  experimentId,
  runId,
  questionId,
  onClose,
}: {
  experimentId: string;
  runId: string;
  questionId: string;
  onClose: () => void;
}) {
  const query = useQuery({
    queryKey: queryKeys.runQuestion(experimentId, runId, questionId),
    queryFn: () => experimentsApi.question(experimentId, runId, questionId),
  });
  const detail = query.data;

  return (
    <aside className="fixed inset-y-0 right-0 z-40 flex w-full max-w-5xl flex-col border-l border-line bg-paper-raised shadow-xl">
      <header className="flex items-center justify-between border-b border-line px-4 py-3">
        <h2 className="text-sm font-semibold">Question</h2>
        <Button variant="ghost" onClick={onClose} aria-label="Close panel">
          ×
        </Button>
      </header>
      <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4 text-sm">
        {query.isLoading ? <Skeleton className="h-40" /> : null}
        {detail ? (
          <>
            <div>
              <p className="font-medium">{detail.text}</p>
              <p className="mt-2 text-xs text-ink-muted">Gold documents</p>
              <ul className="font-mono text-xs">
                {detail.gold_documents.map((doc) => (
                  <li key={doc.document_id}>{doc.filename}</li>
                ))}
              </ul>
            </div>
            <div
              className="grid gap-4"
              style={{
                gridTemplateColumns: `repeat(${Math.max(detail.variants.length, 1)}, minmax(14rem, 1fr))`,
              }}
            >
              {detail.variants.map((variant) => (
                <section key={variant.variant_id} className="min-w-0">
                  <h3 className="mb-2 font-semibold">
                    {variant.name}{" "}
                    {variant.is_baseline ? <Badge tone="info">baseline</Badge> : null}
                  </h3>
                  {detail.answerable ? (
                    <VariantEvidence
                      variant={variant}
                      qaSetId={detail.qa_set_id}
                      questionId={detail.question_id}
                    />
                  ) : null}
                  {variant.executions.map((execution) => (
                    <div key={execution.execution_id} className="mb-3">
                      {variant.executions.length > 1 ? (
                        <p className="mb-1 text-xs text-ink-muted">
                          Repetition {execution.repetition}
                        </p>
                      ) : null}
                      {execution.excluded_reason ? (
                        <p className="text-xs text-ink-muted">
                          Documents excluded: {execution.excluded_reason}
                        </p>
                      ) : null}
                      {execution.chunk_excluded_reason ? (
                        <p className="text-xs text-ink-muted">
                          Chunks excluded: {execution.chunk_excluded_reason}
                        </p>
                      ) : null}
                      {execution.error ? (
                        <p className="text-xs text-danger">{execution.error}</p>
                      ) : null}
                      <Calls calls={execution.calls ?? []} />
                      <ul className="space-y-2">
                        {execution.hits.map((hit, index) => (
                          <Hit key={`${index}-${hit.chunk_id}`} hit={hit} />
                        ))}
                      </ul>
                    </div>
                  ))}
                </section>
              ))}
            </div>
          </>
        ) : null}
      </div>
    </aside>
  );
}
