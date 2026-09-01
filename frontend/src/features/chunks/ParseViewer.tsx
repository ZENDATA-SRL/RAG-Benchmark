import { useQuery } from "@tanstack/react-query";

import { inspectionApi } from "@/api/resources";
import { Button } from "@/components/ui/Button";
import { queryKeys } from "@/lib/queryClient";

export function ParseViewer({
  documentId,
  parsingProfileId,
  page,
}: {
  documentId: string;
  parsingProfileId: string;
  page: number;
}) {
  const offset = Math.max(0, page - 1);
  const query = useQuery({
    queryKey: [...queryKeys.parse(documentId, parsingProfileId), offset],
    queryFn: () => inspectionApi.parse(documentId, parsingProfileId, offset),
    enabled: Boolean(parsingProfileId),
  });

  if (!parsingProfileId) {
    return <p className="p-4 text-sm text-ink-muted">Materialise first to inspect the parse.</p>;
  }
  if (query.isError) {
    return (
      <p className="p-4 text-sm text-ink-muted">
        Parse is not ready for this profile. If chunks look wrong, this tab is how you tell whether the parser lost
        the page.
      </p>
    );
  }
  const current = query.data?.items?.[0];
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-line px-3 py-2 text-xs text-ink-muted">
        <span>
          Parse page {current?.page ?? page}
          {query.data ? ` of ${query.data.total}` : ""}
        </span>
        <Button variant="ghost" onClick={() => query.refetch()}>
          Refresh
        </Button>
      </div>
      <pre className="flex-1 overflow-auto p-4 text-sm whitespace-pre-wrap">
        {current?.text || "No text on this page."}
      </pre>
    </div>
  );
}
