import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { experimentsApi } from "@/api/resources";
import type { ExperimentRead } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { TableSkeleton } from "@/components/ui/Skeleton";
import { TableFrame } from "@/components/ui/TableFrame";
import { formatDate } from "@/lib/format";
import { queryKeys } from "@/lib/queryClient";

import { ExperimentWizard } from "./ExperimentWizard";

type QaSetGroup = { qaSetId: string; qaSetName: string; items: ExperimentRead[] };
type CorpusGroup = { corpusId: string; corpusName: string; qaSets: QaSetGroup[] };

// Experiments are only comparable on the same corpus and the same questions, so the list is
// split by corpus first and by QA set inside it; groups are sorted by name and each table
// keeps the API order (newest first).
function groupExperiments(items: ExperimentRead[]): CorpusGroup[] {
  const corpora = new Map<string, CorpusGroup>();
  for (const experiment of items) {
    const corpusId = experiment.corpus_id ?? "";
    const qaSetId = experiment.qa_set_id ?? "";
    let corpus = corpora.get(corpusId);
    if (!corpus) {
      corpus = { corpusId, corpusName: experiment.corpus_name ?? "Unknown corpus", qaSets: [] };
      corpora.set(corpusId, corpus);
    }
    let qaSet = corpus.qaSets.find((group) => group.qaSetId === qaSetId);
    if (!qaSet) {
      qaSet = { qaSetId, qaSetName: experiment.qa_set_name ?? "Unknown QA set", items: [] };
      corpus.qaSets.push(qaSet);
    }
    qaSet.items.push(experiment);
  }
  const byName = (a: string, b: string) => a.localeCompare(b);
  return [...corpora.values()]
    .map((corpus) => ({
      ...corpus,
      qaSets: corpus.qaSets.sort((a, b) => byName(a.qaSetName, b.qaSetName)),
    }))
    .sort((a, b) => byName(a.corpusName, b.corpusName));
}

export function ExperimentsPage() {
  const [creating, setCreating] = useState(false);
  const experiments = useQuery({ queryKey: queryKeys.experiments, queryFn: experimentsApi.list });
  const items = experiments.data?.items;
  const groups = useMemo(() => groupExperiments(items ?? []), [items]);

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
      {experiments.isSuccess && groups.length === 0 ? (
        <EmptyState
          title="No experiment yet"
          body="You need a corpus snapshot with a ready index build and a frozen QA set."
          action={<Button onClick={() => setCreating(true)}>Create an experiment</Button>}
        />
      ) : null}

      <div className="space-y-10">
        {groups.map((corpus) => (
          <section key={corpus.corpusId} data-testid="experiment-corpus-group">
            <h2 className="mb-3 flex items-baseline gap-2 border-b border-line pb-1 text-lg font-semibold">
              <span className="text-xs font-normal tracking-wide text-ink-muted uppercase">
                Corpus
              </span>
              {corpus.corpusId ? (
                <Link to={`/corpora/${corpus.corpusId}`} className="hover:underline">
                  {corpus.corpusName}
                </Link>
              ) : (
                <span>{corpus.corpusName}</span>
              )}
            </h2>
            <div className="space-y-6">
              {corpus.qaSets.map((qaSet) => (
                <div key={qaSet.qaSetId}>
                  <h3 className="mb-2 flex items-baseline gap-2 text-sm font-semibold">
                    <span className="text-xs font-normal text-ink-muted">QA set</span>
                    {qaSet.qaSetId ? (
                      <Link to={`/qa-sets/${qaSet.qaSetId}`} className="hover:underline">
                        {qaSet.qaSetName}
                      </Link>
                    ) : (
                      <span>{qaSet.qaSetName}</span>
                    )}
                    <span className="text-xs font-normal text-ink-muted">
                      {qaSet.items.length} {qaSet.items.length === 1 ? "experiment" : "experiments"}
                    </span>
                  </h3>
                  <ExperimentTable items={qaSet.items} />
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>

      {creating ? <ExperimentWizard onClose={() => setCreating(false)} /> : null}
    </div>
  );
}

function ExperimentTable({ items }: { items: ExperimentRead[] }) {
  return (
    <TableFrame>
      <table className="w-full text-left text-sm">
        <thead className="border-b border-line bg-paper text-xs text-ink-muted">
          <tr>
            <th className="px-4 py-2 font-medium">Name</th>
            <th className="px-4 py-2 font-medium">Snapshots (corpus · QA)</th>
            <th className="px-4 py-2 font-medium">Variants</th>
            <th className="px-4 py-2 font-medium">Repetitions</th>
            <th className="px-4 py-2 font-medium">Created</th>
          </tr>
        </thead>
        <tbody>
          {items.map((experiment) => (
            <tr key={experiment.id} className="border-b border-line last:border-0">
              <td className="px-4 py-3">
                <Link to={`/experiments/${experiment.id}`} className="font-medium hover:underline">
                  {experiment.name}
                </Link>
              </td>
              <td className="px-4 py-3 text-xs text-ink-muted">
                {experiment.corpus_snapshot_label ?? "—"} ·{" "}
                {experiment.qa_set_snapshot_label ?? "—"}
              </td>
              <td className="px-4 py-3">{experiment.variant_count}</td>
              <td className="px-4 py-3">{experiment.repetitions}</td>
              <td className="px-4 py-3 text-ink-muted">{formatDate(experiment.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </TableFrame>
  );
}
