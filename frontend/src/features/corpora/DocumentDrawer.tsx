import { useQuery } from "@tanstack/react-query";

import { documentContentUrl } from "@/api/client";
import { documentsApi } from "@/api/resources";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { formatBytes, formatDate, shortHash } from "@/lib/format";
import { queryKeys } from "@/lib/queryClient";

function statusTone(status: string): "good" | "bad" | "warn" | "neutral" {
  if (status === "stored") return "good";
  if (status === "failed") return "bad";
  if (status === "fetching") return "warn";
  return "neutral";
}

export function DocumentDrawer({
  documentId,
  onClose,
}: {
  documentId: string;
  onClose: () => void;
}) {
  const query = useQuery({
    queryKey: queryKeys.document(documentId),
    queryFn: () => documentsApi.get(documentId),
  });

  const document = query.data;

  return (
    <aside className="flex w-96 shrink-0 flex-col border-l border-line bg-paper-raised">
      <header className="flex items-center justify-between border-b border-line px-4 py-3">
        <h2 className="text-sm font-semibold">Document</h2>
        <Button variant="ghost" onClick={onClose} aria-label="Close panel">
          ×
        </Button>
      </header>
      <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4 text-sm">
        {query.isLoading ? <Skeleton className="h-40" /> : null}
        {document ? (
          <>
            <div>
              <p className="font-medium">{document.filename}</p>
              <div className="mt-2 flex flex-wrap gap-2">
                <Badge tone={statusTone(document.status)}>{document.status}</Badge>
                <span className="text-ink-muted">{formatBytes(document.size_bytes)}</span>
              </div>
            </div>
            <dl className="space-y-2">
              <div>
                <dt className="text-xs text-ink-muted">Content hash</dt>
                <dd className="font-mono text-xs break-all">{document.content_hash}</dd>
              </div>
              <div>
                <dt className="text-xs text-ink-muted">Acquired</dt>
                <dd>{formatDate(document.created_at)}</dd>
              </div>
              <div>
                <dt className="text-xs text-ink-muted">MIME</dt>
                <dd>{document.mime_type}</dd>
              </div>
              {document.error ? (
                <div>
                  <dt className="text-xs text-ink-muted">Acquisition error</dt>
                  <dd className="text-danger">{document.error}</dd>
                </div>
              ) : null}
            </dl>
            <section>
              <h3 className="text-xs font-semibold tracking-wide text-ink-muted uppercase">
                Provenance
              </h3>
              {(document.provenances ?? []).length === 0 ? (
                <p className="mt-1 text-ink-muted">No origin recorded.</p>
              ) : (
                <ul className="mt-2 space-y-2">
                  {(document.provenances ?? []).map((provenance) => (
                    <li key={provenance.id} className="rounded-md border border-line px-2 py-2">
                      <a
                        href={provenance.original_uri}
                        className="text-rust break-all underline-offset-2 hover:underline"
                        target="_blank"
                        rel="noreferrer"
                      >
                        {provenance.original_uri}
                      </a>
                      <p className="mt-1 font-mono text-[11px] text-ink-muted">
                        {shortHash(provenance.connection_id, 8)} · {formatDate(provenance.created_at)}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </section>
            <Button
              variant="secondary"
              className="w-full"
              onClick={() => window.open(documentContentUrl(document.id), "_blank")}
            >
              Download original
            </Button>
          </>
        ) : null}
      </div>
    </aside>
  );
}
