import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import {
  configurationsApi,
  corporaApi,
  inspectionApi,
  qaSetsApi,
  questionsApi,
} from "@/api/resources";
import type { EvidenceRead, QuestionRead, RelevanceGrade } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { TableSkeleton } from "@/components/ui/Skeleton";
import { queryKeys } from "@/lib/queryClient";
import { toast } from "@/lib/toast";

import { ChunkViewer, toNavigable } from "../chunks/ChunkViewer";
import type { NavigableChunk } from "../chunks/types";
import {
  draftFromEvidence,
  evidencePayload,
  loadAnnotator,
  nextToReview,
  sameDraft,
  saveAnnotator,
  setRelevance,
  type DraftChunk,
  type EvidenceDecision,
} from "./evidence";
import { EvidencePanel, EvidenceStatusBadge } from "./EvidencePanel";

/** Keys that mark the selected chunk; ignored while typing in a field. */
const RELEVANCE_KEYS: Record<string, RelevanceGrade | null> = {
  s: "sufficient",
  p: "supporting",
  x: null,
};

export function AnnotationPage() {
  const { qaSetId = "", questionId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const configurationId = params.get("configuration") ?? "";

  const configurations = useQuery({
    queryKey: queryKeys.configurations,
    queryFn: configurationsApi.list,
  });
  const qaSet = useQuery({
    queryKey: queryKeys.qaSet(qaSetId, configurationId),
    queryFn: () => qaSetsApi.get(qaSetId, configurationId || undefined),
    enabled: Boolean(configurationId),
  });
  const question = useQuery({
    queryKey: queryKeys.question(questionId, configurationId),
    queryFn: () => questionsApi.get(questionId, configurationId || undefined),
  });
  const evidence = useQuery({
    queryKey: queryKeys.evidence(questionId, configurationId),
    queryFn: () => questionsApi.evidence(questionId, configurationId),
    enabled: Boolean(configurationId),
  });

  const configuration = configurations.data?.items.find((item) => item.id === configurationId);
  const next = nextToReview(qaSet.data?.questions.items ?? [], questionId);
  const goTo = (id: string) =>
    navigate(`/qa-sets/${qaSetId}/questions/${id}/annotate?configuration=${configurationId}`);

  return (
    <div>
      <p className="mb-2 text-sm">
        <Link to="/qa-sets" className="text-rust hover:underline">
          QA sets
        </Link>
        <span className="text-ink-muted"> / </span>
        <Link
          to={`/qa-sets/${qaSetId}?configuration=${configurationId}`}
          className="text-rust hover:underline"
        >
          {qaSet.data?.name ?? "QA set"}
        </Link>
        <span className="text-ink-muted"> / annotate</span>
      </p>

      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <QuestionHeader question={question.data} />
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <label>
            <span className="mr-2 text-ink-muted">Configuration</span>
            <select
              value={configurationId}
              onChange={(event) => {
                const nextParams = new URLSearchParams(params);
                nextParams.set("configuration", event.target.value);
                setParams(nextParams);
              }}
              className="rounded-md border border-line bg-paper-raised px-2 py-1"
            >
              <option value="">Choose…</option>
              {(configurations.data?.items ?? []).map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          {configurationId ? (
            next ? (
              <button
                type="button"
                className="text-rust hover:underline"
                onClick={() => goTo(next)}
                data-testid="next-to-review"
              >
                Next to review →
              </button>
            ) : (
              <span className="text-xs text-ink-muted">Nothing else to review</span>
            )
          ) : null}
        </div>
      </div>

      {!configurationId ? (
        <EmptyState
          title="Choose a chunking configuration"
          body="Evidence is confirmed per chunking configuration: the chunks of another parser or chunker are other chunks. The configuration you annotate with is also the finest granularity chunk-level metrics can have."
        />
      ) : question.data && !question.data.answerable ? (
        <EmptyState
          title="This question is not answerable"
          body="It is flagged as having no answer in the documents, so there is no evidence to review."
        />
      ) : question.data && evidence.data ? (
        <Workbench
          // Remounted per question and configuration, so the draft starts from what is saved.
          key={`${questionId}:${configurationId}`}
          qaSetId={qaSetId}
          originCorpusId={qaSet.data?.origin_corpus_id ?? null}
          question={question.data}
          evidence={evidence.data}
          configurationId={configurationId}
          parsingProfileId={configuration?.parsing_profile_id}
          documentId={params.get("document")}
          onDocument={(id) => {
            const nextParams = new URLSearchParams(params);
            nextParams.set("document", id);
            setParams(nextParams, { replace: true });
          }}
        />
      ) : (
        <TableSkeleton />
      )}
    </div>
  );
}

function QuestionHeader({ question }: { question: QuestionRead | undefined }) {
  if (!question) return <div className="h-12" />;
  const answer = question.expected_answers[0]?.text;
  return (
    <div className="max-w-3xl">
      <div className="flex items-center gap-2">
        <h1 className="text-xl font-semibold" data-testid="annotated-question">
          {question.text}
        </h1>
        {question.evidence_status ? (
          <EvidenceStatusBadge status={question.evidence_status} />
        ) : null}
        {question.frozen ? <Badge>frozen</Badge> : null}
      </div>
      <p className="mt-1 text-sm text-ink-muted">
        {answer ? (
          <>
            <span className="font-medium text-ink">Expected answer: </span>
            {answer}
          </>
        ) : (
          "No expected answer"
        )}
      </p>
    </div>
  );
}

function Workbench({
  qaSetId,
  originCorpusId,
  question,
  evidence,
  configurationId,
  parsingProfileId,
  documentId,
  onDocument,
}: {
  qaSetId: string;
  originCorpusId: string | null;
  question: QuestionRead;
  evidence: EvidenceRead;
  configurationId: string;
  parsingProfileId?: string;
  documentId: string | null;
  onDocument: (id: string) => void;
}) {
  const queryClient = useQueryClient();
  const [saved, setSaved] = useState(evidence);
  const [draft, setDraft] = useState<DraftChunk[]>(() => draftFromEvidence(evidence));
  const [annotator, setAnnotator] = useState(loadAnnotator);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  const corpusDocuments = useQuery({
    queryKey: queryKeys.corpusDocuments(originCorpusId ?? ""),
    queryFn: () => corporaApi.documents(originCorpusId ?? ""),
    enabled: Boolean(originCorpusId),
  });

  // Gold documents first, then the documents the draft points into, then the corpus.
  const documents = useMemo(() => {
    const seen = new Map<string, { id: string; filename: string; gold: boolean }>();
    for (const doc of question.gold_documents) {
      seen.set(doc.document_id, { id: doc.document_id, filename: doc.filename, gold: true });
    }
    for (const chunk of draft) {
      if (!seen.has(chunk.document_id)) {
        seen.set(chunk.document_id, {
          id: chunk.document_id,
          filename: chunk.filename,
          gold: false,
        });
      }
    }
    for (const doc of corpusDocuments.data?.items ?? []) {
      if (!seen.has(doc.id)) seen.set(doc.id, { id: doc.id, filename: doc.filename, gold: false });
    }
    return [...seen.values()];
  }, [question.gold_documents, draft, corpusDocuments.data]);

  const activeDocumentId = documentId ?? documents[0]?.id ?? "";
  const activeDocument = documents.find((doc) => doc.id === activeDocumentId);

  const chunks = useQuery({
    queryKey: queryKeys.allChunks(activeDocumentId, configurationId),
    queryFn: () => inspectionApi.allChunks(activeDocumentId, configurationId),
    enabled: Boolean(activeDocumentId),
    meta: { silent: true },
  });
  const navigable = useMemo(() => {
    const all = (chunks.data?.items ?? []).map(toNavigable);
    const needle = filter.trim().toLowerCase();
    return needle ? all.filter((chunk) => chunk.text.toLowerCase().includes(needle)) : all;
  }, [chunks.data, filter]);
  const grades = new Map(draft.map((item) => [item.chunk_id, item.relevance]));

  const mark = (chunk: NavigableChunk, relevance: RelevanceGrade | null) =>
    setDraft((current) =>
      setRelevance(
        current,
        {
          chunk_id: chunk.id,
          document_id: activeDocumentId,
          filename: activeDocument?.filename ?? "",
          ordinal: chunk.ordinal,
          text: chunk.text,
        },
        relevance,
      ),
    );

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      if (!(event.key in RELEVANCE_KEYS) || !selectedId) return;
      const chunk = navigable.find((item) => item.id === selectedId);
      if (!chunk) return;
      event.preventDefault();
      mark(chunk, RELEVANCE_KEYS[event.key]);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const save = useMutation({
    mutationFn: (decision: EvidenceDecision) =>
      questionsApi.saveEvidence(
        question.id,
        evidencePayload(configurationId, decision, draft, annotator),
      ),
    onSuccess: async (result) => {
      setSaved(result);
      setDraft(draftFromEvidence(result));
      saveAnnotator(annotator);
      const added = result.added_gold_document_ids?.length ?? 0;
      if (added > 0) {
        toast.success(`Added ${added} document(s) to the gold documents.`);
      }
      queryClient.setQueryData(queryKeys.evidence(question.id, configurationId), result);
      await queryClient.invalidateQueries({ queryKey: queryKeys.qaSetScope(qaSetId) });
      await queryClient.invalidateQueries({ queryKey: ["questions", question.id] });
    },
  });

  return (
    <div className="grid gap-4 lg:grid-cols-[20rem_1fr]">
      <aside className="flex h-[calc(100vh-11rem)] min-h-[30rem] flex-col overflow-hidden rounded-xl border border-line bg-paper-raised">
        <div className="space-y-2 border-b border-line px-3 py-2 text-sm">
          <label className="block">
            <span className="mb-1 block text-xs text-ink-muted">Document</span>
            <select
              value={activeDocumentId}
              onChange={(event) => {
                setSelectedId(null);
                onDocument(event.target.value);
              }}
              className="w-full rounded-md border border-line bg-paper-raised px-2 py-1"
              data-testid="annotation-document"
            >
              {documents.map((doc) => (
                <option key={doc.id} value={doc.id}>
                  {doc.gold ? "★ " : ""}
                  {doc.filename}
                </option>
              ))}
            </select>
          </label>
          <input
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            placeholder="Filter chunks by text"
            aria-label="Filter chunks by text"
            className="w-full rounded-md border border-line bg-paper-raised px-2 py-1"
          />
          <p className="text-[11px] text-ink-muted">
            ★ gold document · keys on the selected chunk: <kbd>s</kbd> sufficient, <kbd>p</kbd>{" "}
            supporting, <kbd>x</kbd> remove, <kbd>↑</kbd>/<kbd>↓</kbd> move
          </p>
        </div>
        <EvidencePanel
          status={saved.status}
          confirmedBy={saved.confirmed_by}
          confirmedAt={saved.confirmed_at}
          draft={draft}
          dirty={!sameDraft(draft, draftFromEvidence(saved))}
          annotator={annotator}
          onAnnotatorChange={setAnnotator}
          onRelevance={(chunk, relevance) =>
            setDraft((current) => setRelevance(current, chunk, relevance ?? null))
          }
          onOpen={(chunk) => {
            onDocument(chunk.document_id);
            setSelectedId(chunk.chunk_id);
          }}
          onSave={(decision) => save.mutate(decision)}
          saving={save.isPending}
        />
      </aside>

      {!activeDocumentId ? (
        <EmptyState
          title="No document to open"
          body="The question has no gold document and the set has no origin corpus to browse."
        />
      ) : chunks.isError ? (
        <EmptyState
          title="Chunks are not ready"
          body="This document is not materialised under the chosen configuration. Materialise the configuration on the corpus first."
        />
      ) : chunks.isLoading ? (
        <TableSkeleton />
      ) : (
        <ChunkViewer
          documentId={activeDocumentId}
          chunks={navigable}
          selectedId={selectedId ?? navigable[0]?.id ?? null}
          onSelect={setSelectedId}
          parsingProfileId={parsingProfileId}
          renderChunkActions={(chunk) => (
            <RelevanceToggle
              ordinal={chunk.ordinal}
              value={grades.get(chunk.id) ?? null}
              onChange={(relevance) => mark(chunk, relevance)}
            />
          )}
        />
      )}
    </div>
  );
}

function RelevanceToggle({
  ordinal,
  value,
  onChange,
}: {
  ordinal: number;
  value: RelevanceGrade | null;
  onChange: (relevance: RelevanceGrade | null) => void;
}) {
  const options: { grade: RelevanceGrade; label: string }[] = [
    { grade: "sufficient", label: "sufficient" },
    { grade: "supporting", label: "supporting" },
  ];
  return (
    <span className="flex gap-1">
      {options.map(({ grade, label }) => (
        <button
          key={grade}
          type="button"
          aria-pressed={value === grade}
          aria-label={`Mark chunk ${ordinal} as ${label}`}
          onClick={(event) => {
            event.stopPropagation();
            onChange(value === grade ? null : grade);
          }}
          className={`rounded-full border px-2 py-0.5 ${
            value === grade
              ? grade === "sufficient"
                ? "border-teal bg-teal/15 text-teal"
                : "border-amber bg-amber/20 text-ink"
              : "border-line text-ink-muted hover:border-ink/30"
          }`}
        >
          {label}
        </button>
      ))}
    </span>
  );
}
