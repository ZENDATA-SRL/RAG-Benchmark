import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { corporaApi, qaSetsApi } from "@/api/resources";
import type { QASetSnapshotCreated } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { TableSkeleton } from "@/components/ui/Skeleton";
import { TableFrame } from "@/components/ui/TableFrame";
import { formatDate, shortHash } from "@/lib/format";
import { queryKeys } from "@/lib/queryClient";

import { ImportDialog } from "./ImportDialog";

function FreezeResult({ result }: { result: QASetSnapshotCreated }) {
  const { snapshot } = result;
  return (
    <div
      className="mb-4 rounded-xl border border-line bg-paper-raised p-4 text-sm"
      data-testid="freeze-result"
    >
      <p className="font-medium">
        {result.created ? "Snapshot frozen" : "No new snapshot"}: {snapshot.label}
      </p>
      {!result.created ? (
        <p className="mt-1 text-ink-muted">
          {result.detail ?? "A snapshot with the same questions already existed."}
        </p>
      ) : null}
      <p className="mt-1 text-xs text-ink-muted">
        {snapshot.question_count} questions · {shortHash(snapshot.composition_hash)} ·{" "}
        {formatDate(snapshot.frozen_at)}
      </p>
    </div>
  );
}

export function QaSetDetailPage() {
  const { qaSetId = "" } = useParams();
  const queryClient = useQueryClient();
  const [importing, setImporting] = useState(false);
  const [frozen, setFrozen] = useState<QASetSnapshotCreated | null>(null);

  const qaSet = useQuery({
    queryKey: queryKeys.qaSet(qaSetId),
    queryFn: () => qaSetsApi.get(qaSetId),
  });
  const snapshots = useQuery({
    queryKey: queryKeys.qaSetSnapshots(qaSetId),
    queryFn: () => qaSetsApi.snapshots(qaSetId),
  });
  const freeze = useMutation({
    mutationFn: () => qaSetsApi.freeze(qaSetId),
    onSuccess: async (result) => {
      setFrozen(result);
      await queryClient.invalidateQueries({ queryKey: queryKeys.qaSetSnapshots(qaSetId) });
    },
  });

  const detail = qaSet.data;
  const questions = detail?.questions.items ?? [];
  const originCorpusId = detail?.origin_corpus_id ?? "";
  const originCorpus = useQuery({
    queryKey: queryKeys.corpus(originCorpusId),
    queryFn: () => corporaApi.get(originCorpusId),
    enabled: Boolean(originCorpusId),
  });

  return (
    <div>
      <p className="mb-2 text-sm">
        <Link to="/qa-sets" className="text-rust hover:underline">
          QA sets
        </Link>
      </p>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">{detail?.name ?? "QA set"}</h1>
          <p className="mt-1 text-sm text-ink-muted">{detail?.description || "No description"}</p>
          {originCorpusId ? (
            <p className="mt-2 text-sm" data-testid="origin-corpus">
              <span className="text-ink-muted">Corpus: </span>
              <Link
                to={`/corpora/${originCorpusId}`}
                className="font-medium text-rust hover:underline"
              >
                {originCorpus.data?.name ?? "…"}
              </Link>
            </p>
          ) : null}
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => setImporting(true)}>
            Import questions
          </Button>
          <Button
            onClick={() => freeze.mutate()}
            disabled={freeze.isPending || questions.length === 0}
          >
            Freeze
          </Button>
        </div>
      </div>

      {frozen ? <FreezeResult result={frozen} /> : null}

      {qaSet.isLoading ? <TableSkeleton /> : null}
      {qaSet.isSuccess && questions.length === 0 ? (
        <EmptyState
          title="No questions yet"
          body="Import a CSV or JSONL file with the questions and their gold files."
          action={<Button onClick={() => setImporting(true)}>Import questions</Button>}
        />
      ) : null}

      {detail && questions.length > 0 ? (
        <p className="mb-2 text-xs text-ink-muted">
          {detail.questions.total > questions.length
            ? `Showing ${questions.length} of ${detail.questions.total} questions`
            : `${questions.length} ${questions.length === 1 ? "question" : "questions"}`}
        </p>
      ) : null}
      {questions.length > 0 ? (
        <TableFrame>
          <table className="w-full text-left text-sm" data-testid="questions-table">
            <thead className="border-b border-line bg-paper text-xs text-ink-muted">
              <tr>
                <th className="px-4 py-2 font-medium">Question</th>
                <th className="px-4 py-2 font-medium">Expected answer</th>
                <th className="px-4 py-2 font-medium">Tags</th>
                <th className="px-4 py-2 font-medium">Answerable</th>
                <th className="px-4 py-2 font-medium">Gold documents</th>
              </tr>
            </thead>
            <tbody>
              {questions.map((question) => (
                <tr key={question.id} className="border-b border-line align-top last:border-0">
                  <td className="px-4 py-3">{question.text}</td>
                  <td className="px-4 py-3 text-ink-muted">
                    {question.expected_answers[0]?.text ?? "—"}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {question.tags.map((tag) => (
                        <Badge key={tag}>{tag}</Badge>
                      ))}
                    </div>
                  </td>
                  <td className="px-4 py-3">{question.answerable ? "yes" : "no"}</td>
                  <td className="px-4 py-3 font-mono text-xs">
                    {question.gold_documents.map((doc) => doc.filename).join(", ") || "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableFrame>
      ) : null}

      <section className="mt-8">
        <h2 className="mb-2 text-sm font-semibold">Snapshots</h2>
        {(snapshots.data?.items ?? []).length === 0 ? (
          <p className="text-sm text-ink-muted">None yet. An experiment uses a frozen snapshot.</p>
        ) : (
          <ul className="space-y-1 text-sm">
            {snapshots.data?.items.map((snapshot) => (
              <li key={snapshot.id}>
                <span className="font-medium">{snapshot.label}</span>{" "}
                <span className="text-ink-muted">
                  · {snapshot.question_count} questions · {formatDate(snapshot.frozen_at)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {importing ? <ImportDialog qaSetId={qaSetId} onClose={() => setImporting(false)} /> : null}
    </div>
  );
}
