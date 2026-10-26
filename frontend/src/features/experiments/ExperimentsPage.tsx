import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { experimentsApi } from "@/api/resources";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { TableSkeleton } from "@/components/ui/Skeleton";
import { formatDate } from "@/lib/format";
import { queryKeys } from "@/lib/queryClient";

import { ExperimentWizard } from "./ExperimentWizard";

export function ExperimentsPage() {
  const [creating, setCreating] = useState(false);
  const experiments = useQuery({ queryKey: queryKeys.experiments, queryFn: experimentsApi.list });
  const items = experiments.data?.items ?? [];

  return (
    <div>
      <div className="mb-6 flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Experiments</h1>
          <p className="mt-1 text-sm text-ink-muted">
            Compare retrieval variants on the same corpus snapshot and the same frozen questions.
          </p>
        </div>
        <Button onClick={() => setCreating(true)}>New experiment</Button>
      </div>

      {experiments.isLoading ? <TableSkeleton /> : null}
      {experiments.isSuccess && items.length === 0 ? (
        <EmptyState
          title="No experiment yet"
          body="You need a corpus snapshot with a ready index build and a frozen QA set."
          action={<Button onClick={() => setCreating(true)}>Create an experiment</Button>}
        />
      ) : null}

      {items.length > 0 ? (
        <div className="overflow-hidden rounded-xl border border-line bg-paper-raised">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-line bg-paper text-xs text-ink-muted">
              <tr>
                <th className="px-4 py-2 font-medium">Name</th>
                <th className="px-4 py-2 font-medium">Variants</th>
                <th className="px-4 py-2 font-medium">Repetitions</th>
                <th className="px-4 py-2 font-medium">Created</th>
              </tr>
            </thead>
            <tbody>
              {items.map((experiment) => (
                <tr key={experiment.id} className="border-b border-line last:border-0">
                  <td className="px-4 py-3">
                    <Link
                      to={`/experiments/${experiment.id}`}
                      className="font-medium hover:underline"
                    >
                      {experiment.name}
                    </Link>
                  </td>
                  <td className="px-4 py-3">{experiment.variant_count}</td>
                  <td className="px-4 py-3">{experiment.repetitions}</td>
                  <td className="px-4 py-3 text-ink-muted">{formatDate(experiment.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {creating ? <ExperimentWizard onClose={() => setCreating(false)} /> : null}
    </div>
  );
}
