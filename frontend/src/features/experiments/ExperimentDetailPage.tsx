import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";

import { experimentsApi } from "@/api/resources";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { TableSkeleton } from "@/components/ui/Skeleton";
import { TableFrame } from "@/components/ui/TableFrame";
import { formatDate } from "@/lib/format";
import { queryKeys } from "@/lib/queryClient";

import { runStatusTone } from "./status";

export function ExperimentDetailPage() {
  const { experimentId = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const experiment = useQuery({
    queryKey: queryKeys.experiment(experimentId),
    queryFn: () => experimentsApi.get(experimentId),
  });
  const launch = useMutation({
    mutationFn: () => experimentsApi.startRun(experimentId),
    onSuccess: async (run) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.experiment(experimentId) });
      navigate(`/experiments/${experimentId}/runs/${run.id}`);
    },
  });

  const detail = experiment.data;

  return (
    <div>
      <p className="mb-2 text-sm">
        <Link to="/experiments" className="text-rust hover:underline">
          Experiments
        </Link>
      </p>
      {experiment.isLoading ? <TableSkeleton /> : null}
      {detail ? (
        <>
          <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
            <div>
              <h1 className="text-2xl font-semibold">{detail.name}</h1>
              {detail.corpus_id || detail.qa_set_id ? (
                <p className="mt-1 text-sm" data-testid="experiment-origin">
                  {detail.corpus_id ? (
                    <>
                      <span className="text-ink-muted">Corpus </span>
                      <Link
                        to={`/corpora/${detail.corpus_id}`}
                        className="font-medium text-rust hover:underline"
                      >
                        {detail.corpus_name}
                      </Link>
                      <span className="text-ink-muted"> ({detail.corpus_snapshot_label})</span>
                    </>
                  ) : null}
                  {detail.corpus_id && detail.qa_set_id ? (
                    <span className="text-ink-muted"> · </span>
                  ) : null}
                  {detail.qa_set_id ? (
                    <>
                      <span className="text-ink-muted">QA set </span>
                      <Link
                        to={`/qa-sets/${detail.qa_set_id}`}
                        className="font-medium text-rust hover:underline"
                      >
                        {detail.qa_set_name}
                      </Link>
                      <span className="text-ink-muted"> ({detail.qa_set_snapshot_label})</span>
                    </>
                  ) : null}
                </p>
              ) : null}
              <p className="mt-1 text-sm text-ink-muted">
                {detail.repetitions} {detail.repetitions === 1 ? "repetition" : "repetitions"} ·{" "}
                {detail.coverage.question_count} questions
                {detail.coverage.uncovered_count > 0
                  ? ` · ${detail.coverage.uncovered_count} excluded from the metrics (gold outside the snapshot)`
                  : ""}
              </p>
            </div>
            <Button onClick={() => launch.mutate()} disabled={launch.isPending}>
              Launch run
            </Button>
          </div>

          <section className="mb-8">
            <h2 className="mb-2 text-sm font-semibold">Variants</h2>
            <TableFrame>
              <table className="w-full text-left text-sm">
                <thead className="border-b border-line bg-paper text-xs text-ink-muted">
                  <tr>
                    <th className="px-4 py-2 font-medium">Variant</th>
                    <th className="px-4 py-2 font-medium">Index build</th>
                    <th className="px-4 py-2 font-medium">Retrieval profile</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.variants.map((variant) => (
                    <tr key={variant.id} className="border-b border-line last:border-0">
                      <td className="px-4 py-3 font-medium">
                        {variant.name}{" "}
                        {variant.is_baseline ? <Badge tone="info">baseline</Badge> : null}
                      </td>
                      <td className="px-4 py-3">{variant.index_build_name}</td>
                      <td className="px-4 py-3">
                        {variant.retrieval_profile_name} · top-{variant.top_k}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableFrame>
          </section>

          <section>
            <h2 className="mb-2 text-sm font-semibold">Runs</h2>
            {detail.runs.length === 0 ? (
              <p className="text-sm text-ink-muted">
                No run yet. Launch one to measure the variants.
              </p>
            ) : (
              <ul className="space-y-2 text-sm">
                {detail.runs.map((run) => (
                  <li key={run.id}>
                    <Link
                      to={`/experiments/${experimentId}/runs/${run.id}`}
                      className="flex items-center gap-3 rounded-md border border-line bg-paper-raised px-4 py-2 hover:border-ink/25"
                    >
                      <Badge tone={runStatusTone(run.status)}>{run.status}</Badge>
                      <span>{formatDate(run.created_at)}</span>
                      <span className="text-ink-muted">
                        {run.progress.succeeded + run.progress.failed}/{run.progress.total}{" "}
                        executions
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      ) : null}
    </div>
  );
}
