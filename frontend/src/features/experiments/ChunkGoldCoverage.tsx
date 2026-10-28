import { useQueries, useQuery } from "@tanstack/react-query";

import { configurationsApi, qaSetsApi } from "@/api/resources";
import { queryKeys } from "@/lib/queryClient";

/**
 * How much chunk-level evidence each configuration of the chosen variants has. Informative
 * only: chunk metrics count the confirmed questions and exclude the others with their
 * reason, and document metrics are valid whatever this says.
 */
export function ChunkGoldCoverage({
  qaSetId,
  configurationIds,
}: {
  qaSetId: string;
  configurationIds: string[];
}) {
  const configurations = useQuery({
    queryKey: queryKeys.configurations,
    queryFn: configurationsApi.list,
  });
  const coverages = useQueries({
    queries: configurationIds.map((id) => ({
      queryKey: queryKeys.evidenceCoverage(qaSetId, id),
      queryFn: () => qaSetsApi.evidenceCoverage(qaSetId, id),
      meta: { silent: true },
    })),
  });
  const names = new Map((configurations.data?.items ?? []).map((item) => [item.id, item.name]));
  if (!qaSetId || configurationIds.length === 0) return null;

  return (
    <div className="rounded-md bg-paper p-3 text-xs leading-5" data-testid="chunk-gold-coverage">
      <p className="mb-1 font-medium">Chunk-level evidence of the variants</p>
      <ul>
        {configurationIds.map((id, index) => {
          const coverage = coverages[index]?.data;
          return (
            <li key={id}>
              {names.get(id) ?? id}:{" "}
              {coverage
                ? `${coverage.confirmed} of ${coverage.answerable} answerable questions confirmed, ${coverage.not_found} not found, ${coverage.to_review + coverage.not_reviewed} still to review`
                : "…"}
            </li>
          );
        })}
      </ul>
      <p className="mt-1 text-ink-muted">
        Chunk metrics are computed on the confirmed questions only; the others are excluded with
        their reason. Document metrics do not depend on it.
      </p>
    </div>
  );
}
