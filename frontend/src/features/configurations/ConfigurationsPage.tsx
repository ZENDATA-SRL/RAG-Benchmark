import { useQueries, useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";

import { configurationsApi, corporaApi } from "@/api/resources";
import type { ChunkingConfigurationExpanded } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { TableSkeleton } from "@/components/ui/Skeleton";
import { lastCorpusId } from "@/lib/format";
import { queryKeys } from "@/lib/queryClient";

import { CoverageBadge } from "./CoverageBadge";

function keyParams(configuration: ChunkingConfigurationExpanded): string {
  const chunker = configuration.chunking_profile;
  const parts = [
    chunker.strategy,
    chunker.chunk_size != null ? `size ${chunker.chunk_size}` : null,
    chunker.overlap != null ? `overlap ${chunker.overlap}` : null,
  ];
  return parts.filter(Boolean).join(" · ");
}

export function ConfigurationsPage() {
  const [params, setParams] = useSearchParams();
  const corpusId = params.get("corpus") ?? lastCorpusId() ?? "";

  const configurations = useQuery({
    queryKey: queryKeys.configurations,
    queryFn: configurationsApi.list,
  });
  const corpora = useQuery({
    queryKey: queryKeys.corpora,
    queryFn: corporaApi.list,
  });

  const items = configurations.data?.items ?? [];
  const coverages = useQueries({
    queries: items.map((item) => ({
      queryKey: queryKeys.coverage(item.id, corpusId),
      queryFn: () => configurationsApi.coverage(item.id, corpusId),
      enabled: Boolean(corpusId),
    })),
  });

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Configurations</h1>
          <p className="mt-1 text-sm text-ink-muted">
            A configuration is a parser paired with a chunker. Identity is the pair, not the name.
          </p>
        </div>
        <Link to="/configurations/new">
          <Button>Compose configuration</Button>
        </Link>
      </div>

      <label className="mb-4 block max-w-sm text-sm">
        <span className="mb-1 block text-ink-muted">Coverage on corpus</span>
        <select
          value={corpusId}
          onChange={(event) => {
            const next = new URLSearchParams(params);
            if (event.target.value) next.set("corpus", event.target.value);
            else next.delete("corpus");
            setParams(next);
          }}
          className="w-full rounded-md border border-line bg-paper-raised px-3 py-1.5"
        >
          <option value="">Select a corpus…</option>
          {(corpora.data?.items ?? []).map((corpus) => (
            <option key={corpus.id} value={corpus.id}>
              {corpus.name}
            </option>
          ))}
        </select>
      </label>

      {configurations.isLoading ? <TableSkeleton /> : null}
      {configurations.isSuccess && items.length === 0 ? (
        <EmptyState
          title="No configurations yet"
          body="Compose a parser and a chunker. Try it on three files before applying it to two hundred."
          action={
            <Link to="/configurations/new">
              <Button>Compose configuration</Button>
            </Link>
          }
        />
      ) : null}

      {items.length > 0 ? (
        <div className="overflow-hidden rounded-xl border border-line bg-paper-raised">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-line bg-paper text-xs text-ink-muted">
              <tr>
                <th className="px-4 py-2 font-medium">Name</th>
                <th className="px-4 py-2 font-medium">Parser</th>
                <th className="px-4 py-2 font-medium">Chunker</th>
                <th className="px-4 py-2 font-medium">Key parameters</th>
                <th className="px-4 py-2 font-medium">Coverage</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, index) => (
                <tr key={item.id} className="border-b border-line last:border-0">
                  <td className="px-4 py-3 font-medium">{item.name}</td>
                  <td className="px-4 py-3">{item.parsing_profile.name}</td>
                  <td className="px-4 py-3">{item.chunking_profile.name}</td>
                  <td className="px-4 py-3 text-ink-muted">{keyParams(item)}</td>
                  <td className="px-4 py-3">
                    <CoverageBadge coverage={coverages[index]?.data} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
