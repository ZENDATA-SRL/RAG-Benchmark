import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { experimentsApi } from "@/api/resources";
import { Button } from "@/components/ui/Button";
import { formatDate } from "@/lib/format";
import { toast } from "@/lib/toast";
import { queryKeys } from "@/lib/queryClient";
import { TableFrame } from "@/components/ui/TableFrame";

import { allVariants, CUTOFFS, DEFAULT_CUTOFF } from "./metrics";
import { describeChunkOutcome, describeOutcome } from "./outcome";
import { QuestionDrilldown } from "./QuestionDrilldown";
import { ResultsTable } from "./ResultsTable";
import { RunProgressPanel } from "./RunProgressPanel";
import { isRunActive } from "./status";

const POLL_MS = 2000;

export function RunPage() {
  const { experimentId = "", runId = "" } = useParams();
  const queryClient = useQueryClient();
  const [cutoff, setCutoff] = useState<number>(DEFAULT_CUTOFF);
  const [tag, setTag] = useState("");
  const [openQuestion, setOpenQuestion] = useState<string | null>(null);

  const run = useQuery({
    queryKey: queryKeys.run(experimentId, runId),
    queryFn: () => experimentsApi.run(experimentId, runId),
    refetchInterval: (current) =>
      current.state.data && !isRunActive(current.state.data) ? false : POLL_MS,
  });
  const active = run.data ? isRunActive(run.data) : true;
  const results = useQuery({
    queryKey: queryKeys.runResults(experimentId, runId, tag),
    queryFn: () => experimentsApi.results(experimentId, runId, tag || undefined),
    refetchInterval: active ? POLL_MS * 2 : false,
    meta: { silent: true },
  });
  const questions = useQuery({
    queryKey: queryKeys.runQuestions(experimentId, runId),
    queryFn: () => experimentsApi.questions(experimentId, runId),
    refetchInterval: active ? POLL_MS * 2 : false,
    meta: { silent: true },
  });

  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: queryKeys.run(experimentId, runId) });
  const cancel = useMutation({
    mutationFn: () => experimentsApi.cancelRun(experimentId, runId),
    onSuccess: refresh,
  });
  const resume = useMutation({
    mutationFn: () => experimentsApi.resumeRun(experimentId, runId),
    onSuccess: async (result) => {
      if (!result.started) toast.info(result.detail ?? "The run is already going.");
      await refresh();
    },
  });

  // Scores the stored hits again on the evidence as it is now; no retrieval is repeated.
  const evaluate = useMutation({
    mutationFn: () => experimentsApi.evaluateRun(experimentId, runId),
    onSuccess: async () => {
      // The run key prefixes its results, questions and drill-downs: all of them change.
      await refresh();
      toast.success("Run re-evaluated on the current evidence.");
    },
  });

  const variants = allVariants(results.data?.groups ?? []);
  const variantNames = new Map(variants.map((v) => [v.variant_id, v.name]));
  const questionItems = questions.data?.items ?? [];
  const tags = [...new Set(questionItems.flatMap((question) => question.tags))].sort();
  const variantIds = variants.map((variant) => variant.variant_id);
  const chunkGold = results.data?.chunk_gold;

  return (
    <div>
      <p className="mb-2 text-sm">
        <Link to={`/experiments/${experimentId}`} className="text-rust hover:underline">
          Experiment
        </Link>
      </p>
      <h1 className="mb-4 text-2xl font-semibold">Run</h1>

      {run.data ? (
        <RunProgressPanel
          run={run.data}
          onCancel={() => cancel.mutate()}
          onResume={() => resume.mutate()}
          busy={cancel.isPending || resume.isPending}
        />
      ) : (
        <p className="text-sm text-ink-muted">Loading run…</p>
      )}

      <section className="mt-8">
        <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
          <h2 className="text-sm font-semibold">Results</h2>
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <label className="flex items-center gap-2">
              Cutoff
              <select
                value={cutoff}
                onChange={(event) => setCutoff(Number(event.target.value))}
                className="rounded-md border border-line bg-paper px-2 py-1"
              >
                {CUTOFFS.map((value) => (
                  <option key={value} value={value}>
                    @{value}
                  </option>
                ))}
              </select>
            </label>
            {tags.length > 0 ? (
              <label className="flex items-center gap-2">
                Tag
                <select
                  value={tag}
                  onChange={(event) => setTag(event.target.value)}
                  className="rounded-md border border-line bg-paper px-2 py-1"
                >
                  <option value="">All questions</option>
                  {tags.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
            <a
              href={experimentsApi.resultsCsvUrl(experimentId, runId)}
              className="text-rust hover:underline"
              download
            >
              Download CSV
            </a>
            <Button
              variant="secondary"
              disabled={active || evaluate.isPending}
              onClick={() => evaluate.mutate()}
              title="Score the stored hits again on the evidence as it is now"
            >
              Re-evaluate
            </Button>
          </div>
        </div>
        <p className="mb-2 text-xs text-ink-muted" data-testid="chunk-gold">
          {chunkGold
            ? `Chunk metrics on the evidence of ${formatDate(chunkGold.evaluated_at)} · fingerprint ${chunkGold.hash.slice(0, 8)}`
            : "Chunk metrics not computed for this run yet: re-evaluate it."}
        </p>
        {results.data ? (
          <ResultsTable results={results.data} cutoff={cutoff} />
        ) : (
          <p className="text-sm text-ink-muted">No results yet.</p>
        )}
      </section>

      <section className="mt-8">
        <h2 className="mb-2 text-sm font-semibold">Questions</h2>
        {questionItems.length === 0 ? (
          <p className="text-sm text-ink-muted">No question evaluated yet.</p>
        ) : (
          <TableFrame>
            <table className="w-full text-left text-sm" data-testid="run-questions">
              <thead className="border-b border-line bg-paper text-xs text-ink-muted">
                <tr>
                  <th className="px-4 py-2 font-medium">Question</th>
                  {variantIds.map((id) => (
                    <th key={id} className="px-4 py-2 font-medium">
                      {variantNames.get(id)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {questionItems.map((question) => (
                  <tr key={question.question_id} className="border-b border-line last:border-0">
                    <td className="px-4 py-3">
                      <button
                        type="button"
                        className="text-left hover:underline"
                        onClick={() => setOpenQuestion(question.question_id)}
                      >
                        {question.text}
                      </button>
                    </td>
                    {variantIds.map((id) => {
                      const outcome = question.outcomes.find((item) => item.variant_id === id);
                      return (
                        <td key={id} className="px-4 py-3 font-mono text-xs whitespace-nowrap">
                          <span className="block">doc: {describeOutcome(outcome)}</span>
                          <span className="block text-ink-muted">
                            chunk: {describeChunkOutcome(outcome)}
                          </span>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </TableFrame>
        )}
      </section>

      {openQuestion ? (
        <QuestionDrilldown
          experimentId={experimentId}
          runId={runId}
          questionId={openQuestion}
          onClose={() => setOpenQuestion(null)}
        />
      ) : null}
    </div>
  );
}
