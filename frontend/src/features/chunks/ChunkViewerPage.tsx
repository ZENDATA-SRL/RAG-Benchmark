import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { configurationsApi, inspectionApi } from "@/api/resources";
import { EmptyState } from "@/components/ui/EmptyState";
import { TableSkeleton } from "@/components/ui/Skeleton";
import { queryKeys } from "@/lib/queryClient";

import { ChunkNavigator } from "./ChunkNavigator";
import { ChunkViewer, toNavigable } from "./ChunkViewer";

export function ChunkViewerPage() {
  const { corpusId = "", documentId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const configurationId = params.get("configuration") ?? "";
  const compareId = params.get("compare") ?? "";
  // A link from a retrieval result opens the viewer on that chunk.
  const [selectedId, setSelectedId] = useState<string | null>(params.get("chunk"));

  const configurations = useQuery({
    queryKey: queryKeys.configurations,
    queryFn: configurationsApi.list,
  });
  const items = configurations.data?.items ?? [];
  const chosen = configurationId || items[0]?.id || "";
  const chosenConfig = items.find((item) => item.id === chosen);

  const chunks = useQuery({
    queryKey: queryKeys.chunks(documentId, chosen),
    queryFn: () => inspectionApi.chunks(documentId, chosen),
    enabled: Boolean(documentId && chosen),
  });

  const compare = useQuery({
    queryKey: queryKeys.compare(documentId, [chosen, compareId]),
    queryFn: () => inspectionApi.compare(documentId, [chosen, compareId]),
    enabled: Boolean(documentId && chosen && compareId && compareId !== chosen),
  });

  const navigable = useMemo(() => (chunks.data?.items ?? []).map(toNavigable), [chunks.data]);
  const activeId =
    selectedId && navigable.some((chunk) => chunk.id === selectedId)
      ? selectedId
      : (navigable[0]?.id ?? null);

  return (
    <div>
      <p className="text-xs text-ink-muted">
        <Link to={`/corpora/${corpusId}`} className="hover:underline">
          Corpus
        </Link>
        <span> / inspect</span>
      </p>
      <div className="mt-2 mb-4 flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-2xl font-semibold">Chunk viewer</h1>
        <div className="flex flex-wrap gap-3 text-sm">
          <label>
            <span className="mr-2 text-ink-muted">Configuration</span>
            <select
              value={chosen}
              onChange={(event) => {
                const next = new URLSearchParams(params);
                next.set("configuration", event.target.value);
                setParams(next);
                setSelectedId(null);
              }}
              className="rounded-md border border-line bg-paper-raised px-2 py-1"
            >
              {items.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className="mr-2 text-ink-muted">Compare</span>
            <select
              value={compareId}
              onChange={(event) => {
                const next = new URLSearchParams(params);
                if (event.target.value) next.set("compare", event.target.value);
                else next.delete("compare");
                setParams(next);
              }}
              className="rounded-md border border-line bg-paper-raised px-2 py-1"
            >
              <option value="">None</option>
              {items
                .filter((item) => item.id !== chosen)
                .map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
            </select>
          </label>
        </div>
      </div>

      {chunks.isLoading ? <TableSkeleton /> : null}
      {chunks.isError ? (
        <EmptyState
          title="Chunks are not ready"
          body="Preview this document or materialise the configuration first. Parsing state lives on the configuration, not on the document."
          action={
            <Link to={`/corpora/${corpusId}`} className="text-rust underline">
              Back to corpus
            </Link>
          }
        />
      ) : null}

      {chunks.isSuccess ? (
        <div className={compareId ? "space-y-4" : ""}>
          <ChunkViewer
            documentId={documentId}
            chunks={navigable}
            selectedId={activeId}
            onSelect={setSelectedId}
            parsingProfileId={chosenConfig?.parsing_profile_id}
          />
          {compare.data ? (
            <div className="grid gap-3 lg:grid-cols-2">
              {(compare.data.sides ?? []).map((side) => (
                <div
                  key={side.chunking_configuration_id}
                  className="h-80 overflow-hidden rounded-xl border border-line"
                >
                  <p className="border-b border-line px-3 py-2 text-xs text-ink-muted">
                    {items.find((item) => item.id === side.chunking_configuration_id)?.name ??
                      side.chunking_configuration_id}
                  </p>
                  <ChunkNavigator
                    chunks={(side.chunks ?? []).map(toNavigable)}
                    selectedId={null}
                    onSelect={() => undefined}
                  />
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
