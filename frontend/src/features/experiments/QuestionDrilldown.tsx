import { useQuery } from "@tanstack/react-query";

import { experimentsApi } from "@/api/resources";
import type { HitDetailRead } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { queryKeys } from "@/lib/queryClient";

import { excerpt } from "./outcome";

function Hit({ hit }: { hit: HitDetailRead }) {
  return (
    <li className="rounded-md border border-line bg-paper px-3 py-2 text-xs" data-testid="hit">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono">#{hit.rank}</span>
        <span className="font-mono text-ink-muted">
          {hit.score === null ? "—" : hit.score.toFixed(3)}
        </span>
        {hit.relevant_document ? <Badge tone="good">gold</Badge> : null}
      </div>
      <p className="mt-1 font-medium break-all">
        {hit.filename ?? "unknown file"}
        {hit.page ? ` · p. ${hit.page}` : ""}
      </p>
      <p className="mt-1 text-ink-muted">{excerpt(hit.text)}</p>
    </li>
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
                  {variant.executions.map((execution) => (
                    <div key={execution.execution_id} className="mb-3">
                      {variant.executions.length > 1 ? (
                        <p className="mb-1 text-xs text-ink-muted">
                          Repetition {execution.repetition}
                        </p>
                      ) : null}
                      {execution.excluded_reason ? (
                        <p className="text-xs text-ink-muted">
                          Excluded: {execution.excluded_reason}
                        </p>
                      ) : null}
                      {execution.error ? (
                        <p className="text-xs text-danger">{execution.error}</p>
                      ) : null}
                      <ul className="space-y-2">
                        {execution.hits.map((hit) => (
                          <Hit key={`${hit.rank}-${hit.chunk_id}`} hit={hit} />
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
