import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { inspectionApi } from "@/api/resources";
import type { ChunkSearchHit, RelevanceGrade } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { queryKeys } from "@/lib/queryClient";

import { RelevanceToggle } from "../qa-sets/RelevanceToggle";
import { compactText } from "./queue";

/** Full-text search over the chunks of a configuration, for evidence no candidate caught. */
export function ChunkSearch({
  configurationId,
  corpusId,
  grades,
  onMark,
  onOpen,
}: {
  configurationId: string;
  corpusId: string | null;
  grades: Map<string, RelevanceGrade>;
  onMark: (hit: ChunkSearchHit, relevance: RelevanceGrade | null) => void;
  onOpen: (hit: ChunkSearchHit) => void;
}) {
  const [draft, setDraft] = useState("");
  const [text, setText] = useState("");
  const results = useQuery({
    queryKey: queryKeys.chunkSearch(configurationId, `${corpusId ?? ""}:${text}`),
    queryFn: () => inspectionApi.search(configurationId, text, corpusId ?? undefined),
    enabled: text.length >= 2,
  });

  return (
    <div className="flex min-h-0 flex-col">
      <form
        className="flex gap-2 border-b border-line p-3"
        onSubmit={(event) => {
          event.preventDefault();
          setText(draft.trim());
        }}
      >
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Words of the passage you are looking for"
          aria-label="Search chunks"
          className="flex-1 rounded-md border border-line bg-paper-raised px-2 py-1 text-sm"
        />
        <Button type="submit" variant="secondary" disabled={draft.trim().length < 2}>
          Search
        </Button>
      </form>
      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {results.data ? (
          <>
            <p className="mb-2 text-xs text-ink-muted">
              {results.data.total} chunk(s)
              {results.data.total > results.data.items.length
                ? `, the first ${results.data.items.length} shown`
                : ""}
            </p>
            <ul className="space-y-2" data-testid="search-results">
              {results.data.items.map((hit) => (
                <li key={hit.chunk_id} className="rounded-lg border border-line p-3 text-sm">
                  <div className="mb-1 flex items-center gap-2 text-xs">
                    <button
                      type="button"
                      className="font-mono text-rust hover:underline"
                      onClick={() => onOpen(hit)}
                    >
                      {hit.filename} #{hit.ordinal}
                      {hit.page ? ` · p. ${hit.page}` : ""}
                    </button>
                    <span className="ml-auto">
                      <RelevanceToggle
                        ordinal={hit.ordinal}
                        value={grades.get(hit.chunk_id) ?? null}
                        onChange={(relevance) => onMark(hit, relevance)}
                      />
                    </span>
                  </div>
                  <p className="line-clamp-6 text-ink-muted">{compactText(hit.text)}</p>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="text-xs text-ink-muted">
            Searches the chunks of this configuration{corpusId ? " in the set's corpus" : ""}, by
            the words they contain.
          </p>
        )}
      </div>
    </div>
  );
}
