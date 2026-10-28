import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { configurationsApi, transfersApi } from "@/api/resources";
import { Badge } from "@/components/ui/Badge";
import { queryKeys } from "@/lib/queryClient";

/** The suggestion and transfer jobs of a QA set, newest first, each linking to its queue. */
export function TransferJobs({ qaSetId }: { qaSetId: string }) {
  const jobs = useQuery({
    queryKey: queryKeys.transfers(qaSetId),
    queryFn: () => transfersApi.list(qaSetId),
    meta: { silent: true },
  });
  const configurations = useQuery({
    queryKey: queryKeys.configurations,
    queryFn: configurationsApi.list,
  });
  const names = new Map((configurations.data?.items ?? []).map((item) => [item.id, item.name]));
  const items = (jobs.data?.items ?? []).slice(0, 5);
  if (items.length === 0) return null;

  return (
    <div className="mb-3 flex flex-wrap items-center gap-2 text-xs" data-testid="transfer-jobs">
      <span className="text-ink-muted">Suggested chunks:</span>
      {items.map((job) => (
        <Link
          key={job.id}
          to={`/transfers/${job.id}`}
          className="flex items-center gap-1 rounded-full border border-line px-2 py-0.5 hover:border-rust"
        >
          <span>
            {job.source_configuration_id
              ? `${names.get(job.source_configuration_id) ?? "…"} → `
              : ""}
            {names.get(job.target_configuration_id) ?? "…"}
          </span>
          <span className="font-mono text-ink-muted">
            {job.progress.reviewed}/{job.progress.total}
          </span>
          {job.status === "running" || job.status === "pending" ? (
            <Badge tone="info">ranking</Badge>
          ) : null}
        </Link>
      ))}
    </div>
  );
}
