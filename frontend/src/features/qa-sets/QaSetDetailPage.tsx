import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { configurationsApi, corporaApi, qaSetsApi, questionsApi } from "@/api/resources";
import type { EvidenceCoverageRead, QASetSnapshotCreated, QuestionRead } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/Dialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { TableSkeleton } from "@/components/ui/Skeleton";
import { TableFrame } from "@/components/ui/TableFrame";
import { formatDate, shortHash } from "@/lib/format";
import { queryKeys } from "@/lib/queryClient";

import { filterQuestions, type StatusFilter } from "./evidence";
import { EvidenceStatusBadge } from "./EvidencePanel";
import { ImportDialog } from "./ImportDialog";
import { QuestionEditor } from "./QuestionEditor";

const FILTERS: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "All questions" },
  { value: "needs_review", label: "To review" },
  { value: "confirmed", label: "Confirmed" },
  { value: "not_found", label: "Not found" },
];

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

function CoverageBar({ coverage }: { coverage: EvidenceCoverageRead }) {
  const items = [
    { label: "confirmed", value: coverage.confirmed },
    { label: "not found", value: coverage.not_found },
    { label: "draft", value: coverage.to_review },
    { label: "not reviewed", value: coverage.not_reviewed },
  ];
  return (
    <p className="text-xs text-ink-muted" data-testid="evidence-coverage">
      Evidence of {coverage.answerable} answerable questions:{" "}
      {items.map((item, index) => (
        <span key={item.label}>
          {index > 0 ? " · " : ""}
          <span className="font-medium text-ink">{item.value}</span> {item.label}
        </span>
      ))}
      {coverage.not_answerable > 0 ? ` · ${coverage.not_answerable} not answerable` : ""}
    </p>
  );
}

function ExportLinks({ qaSetId, snapshotId }: { qaSetId: string; snapshotId?: string }) {
  return (
    <span className="inline-flex gap-2 text-xs">
      {(["csv", "jsonl"] as const).map((format) => (
        <a
          key={format}
          href={qaSetsApi.exportUrl(qaSetId, format, snapshotId)}
          download
          className="text-rust hover:underline"
        >
          {format.toUpperCase()}
        </a>
      ))}
    </span>
  );
}

export function QaSetDetailPage() {
  const { qaSetId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const configurationId = params.get("configuration") ?? "";
  const queryClient = useQueryClient();
  const [importing, setImporting] = useState(false);
  const [editing, setEditing] = useState<QuestionRead | "new" | null>(null);
  const [deleting, setDeleting] = useState<QuestionRead | null>(null);
  const [frozen, setFrozen] = useState<QASetSnapshotCreated | null>(null);
  const [filter, setFilter] = useState<StatusFilter>("all");

  const qaSet = useQuery({
    queryKey: queryKeys.qaSet(qaSetId, configurationId),
    queryFn: () => qaSetsApi.get(qaSetId, configurationId || undefined),
  });
  const configurations = useQuery({
    queryKey: queryKeys.configurations,
    queryFn: configurationsApi.list,
  });
  const coverage = useQuery({
    queryKey: queryKeys.evidenceCoverage(qaSetId, configurationId),
    queryFn: () => qaSetsApi.evidenceCoverage(qaSetId, configurationId),
    enabled: Boolean(configurationId),
  });
  const snapshots = useQuery({
    queryKey: queryKeys.qaSetSnapshots(qaSetId),
    queryFn: () => qaSetsApi.snapshots(qaSetId),
  });
  const freeze = useMutation({
    mutationFn: () => qaSetsApi.freeze(qaSetId),
    onSuccess: async (result) => {
      setFrozen(result);
      await queryClient.invalidateQueries({ queryKey: queryKeys.qaSetScope(qaSetId) });
    },
  });
  const remove = useMutation({
    mutationFn: (questionId: string) => questionsApi.remove(questionId),
    onSuccess: async () => {
      setDeleting(null);
      await queryClient.invalidateQueries({ queryKey: queryKeys.qaSetScope(qaSetId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.qaSets });
    },
  });

  const detail = qaSet.data;
  const questions = detail?.questions.items ?? [];
  const shown = configurationId ? filterQuestions(questions, filter) : questions;
  const originCorpusId = detail?.origin_corpus_id ?? "";
  const originCorpus = useQuery({
    queryKey: queryKeys.corpus(originCorpusId),
    queryFn: () => corporaApi.get(originCorpusId),
    enabled: Boolean(originCorpusId),
  });
  const annotateUrl = (questionId: string) =>
    `/qa-sets/${qaSetId}/questions/${questionId}/annotate?configuration=${configurationId}`;

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
        <div className="flex flex-wrap items-center gap-2">
          <span className="mr-2 text-xs text-ink-muted">
            Export <ExportLinks qaSetId={qaSetId} />
          </span>
          <Button variant="secondary" onClick={() => setEditing("new")}>
            New question
          </Button>
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

      <div className="mb-3 flex flex-wrap items-center gap-3 text-sm">
        <label>
          <span className="mr-2 text-ink-muted">Evidence under</span>
          <select
            value={configurationId}
            onChange={(event) => {
              const next = new URLSearchParams(params);
              if (event.target.value) next.set("configuration", event.target.value);
              else next.delete("configuration");
              setParams(next);
            }}
            className="rounded-md border border-line bg-paper-raised px-2 py-1"
            data-testid="evidence-configuration"
          >
            <option value="">No configuration</option>
            {(configurations.data?.items ?? []).map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        {configurationId ? (
          <select
            aria-label="Filter by evidence status"
            value={filter}
            onChange={(event) => setFilter(event.target.value as StatusFilter)}
            className="rounded-md border border-line bg-paper-raised px-2 py-1"
          >
            {FILTERS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        ) : (
          <span className="text-xs text-ink-muted">
            Choose the chunking configuration to review the evidence chunks with.
          </span>
        )}
        {coverage.data ? <CoverageBar coverage={coverage.data} /> : null}
      </div>

      {qaSet.isLoading ? <TableSkeleton /> : null}
      {qaSet.isSuccess && questions.length === 0 ? (
        <EmptyState
          title="No questions yet"
          body="Write a question, or import a CSV or JSONL file with the questions and their gold files."
          action={<Button onClick={() => setEditing("new")}>New question</Button>}
        />
      ) : null}

      {detail && questions.length > 0 ? (
        <p className="mb-2 text-xs text-ink-muted">
          {detail.questions.total > questions.length
            ? `Showing ${questions.length} of ${detail.questions.total} questions`
            : `${questions.length} ${questions.length === 1 ? "question" : "questions"}`}
          {shown.length !== questions.length ? ` · ${shown.length} match the filter` : ""}
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
                {configurationId ? <th className="px-4 py-2 font-medium">Evidence</th> : null}
                <th className="px-4 py-2 font-medium" />
              </tr>
            </thead>
            <tbody>
              {shown.map((question) => (
                <tr key={question.id} className="border-b border-line align-top last:border-0">
                  <td className="px-4 py-3">
                    {question.text}
                    {question.frozen ? (
                      <Badge className="ml-2" tone="neutral">
                        frozen
                      </Badge>
                    ) : null}
                  </td>
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
                  {configurationId ? (
                    <td className="px-4 py-3">
                      {question.answerable && question.evidence_status ? (
                        <EvidenceStatusBadge status={question.evidence_status} />
                      ) : (
                        <span className="text-xs text-ink-muted">—</span>
                      )}
                    </td>
                  ) : null}
                  <td className="px-4 py-3 whitespace-nowrap">
                    <div className="flex justify-end gap-2 text-xs">
                      {configurationId && question.answerable ? (
                        <Link to={annotateUrl(question.id)} className="text-rust hover:underline">
                          Annotate
                        </Link>
                      ) : null}
                      <button
                        type="button"
                        className="text-rust hover:underline"
                        onClick={() => setEditing(question)}
                      >
                        {question.frozen ? "Replace" : "Edit"}
                      </button>
                      {!question.frozen ? (
                        <button
                          type="button"
                          className="text-danger hover:underline"
                          onClick={() => setDeleting(question)}
                        >
                          Delete
                        </button>
                      ) : null}
                    </div>
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
                  · {snapshot.question_count} questions · {formatDate(snapshot.frozen_at)} ·{" "}
                </span>
                <ExportLinks qaSetId={qaSetId} snapshotId={snapshot.id} />
              </li>
            ))}
          </ul>
        )}
      </section>

      {importing ? <ImportDialog qaSetId={qaSetId} onClose={() => setImporting(false)} /> : null}
      {editing ? (
        <QuestionEditor
          qaSetId={qaSetId}
          originCorpusId={detail?.origin_corpus_id ?? null}
          question={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
        />
      ) : null}
      {deleting ? (
        <ConfirmDialog
          title="Delete question"
          body={`“${deleting.text}” is deleted with its expected answers and evidence. No snapshot holds it, so no experiment is affected.`}
          confirmLabel="Delete"
          pending={remove.isPending}
          onConfirm={() => remove.mutate(deleting.id)}
          onClose={() => setDeleting(null)}
        />
      ) : null}
    </div>
  );
}
