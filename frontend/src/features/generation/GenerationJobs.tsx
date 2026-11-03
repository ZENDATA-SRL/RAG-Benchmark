import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { generationApi } from "@/api/resources";
import { Badge } from "@/components/ui/Badge";
import { queryKeys } from "@/lib/queryClient";

import { isActive } from "./generation";

/** The generation jobs of a QA set, newest first, each linking to its review queue. */
export function GenerationJobs({ qaSetId }: { qaSetId: string }) {
  const jobs = useQuery({
    queryKey: queryKeys.generations(qaSetId),
    queryFn: () => generationApi.list(qaSetId),
    meta: { silent: true },
  });
  const items = (jobs.data?.items ?? []).slice(0, 5);
  if (items.length === 0) return null;

  return (
    <div className="mb-3 flex flex-wrap items-center gap-2 text-xs" data-testid="generation-jobs">
      <span className="text-ink-muted">Generated questions:</span>
      {items.map((job) => {
        const { proposals } = job.progress;
        return (
          <Link
            key={job.id}
            to={`/generation-jobs/${job.id}`}
            className="flex items-center gap-1 rounded-full border border-line px-2 py-0.5 hover:border-rust"
          >
            <span>{String(job.params.model ?? "")}</span>
            <span className="font-mono text-ink-muted">
              {proposals.accepted + proposals.rejected}/
              {proposals.pending + proposals.accepted + proposals.rejected}
            </span>
            {isActive(job) ? <Badge tone="info">generating</Badge> : null}
            {job.status === "failed" ? <Badge tone="bad">failed</Badge> : null}
          </Link>
        );
      })}
    </div>
  );
}
