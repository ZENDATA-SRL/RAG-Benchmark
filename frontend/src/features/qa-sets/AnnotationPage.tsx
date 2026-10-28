import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import {
  configurationsApi,
  corporaApi,
  inspectionApi,
  qaSetsApi,
  questionsApi,
  transfersApi,
} from "@/api/resources";
import type { EvidenceRead, QuestionRead, QuestionReviewRead, RelevanceGrade } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { TableSkeleton } from "@/components/ui/Skeleton";
import { queryKeys } from "@/lib/queryClient";
import { toast } from "@/lib/toast";

import { ChunkViewer, toNavigable } from "../chunks/ChunkViewer";
import type { NavigableChunk } from "../chunks/types";
import { CandidateList } from "../transfers/CandidateList";
import { ChunkSearch } from "../transfers/ChunkSearch";
import { candidateChunk, formatScore, initialDraft } from "../transfers/queue";
import {
  blockedReason,
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
import { RelevanceToggle } from "./RelevanceToggle";

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
  // Set when the page reviews the questions of a suggestion job one after the other.
  const transferId = params.get("transfer") ?? "";

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
  const review = useQuery({
    queryKey: queryKeys.transferQuestion(transferId, questionId),
    queryFn: () => transfersApi.question(transferId, questionId),
    enabled: Boolean(transferId),
  });

  const configuration = configurations.data?.items.find((item) => item.id === configurationId);
  const next = nextToReview(qaSet.data?.questions.items ?? [], questionId);
  const goTo = (id: string) =>
    navigate(
      `/qa-sets/${qaSetId}/questions/${id}/annotate?configuration=${configurationId}${
        transferId ? `&transfer=${transferId}` : ""
      }`,
    );
  const afterDecision = () => {
    const nextInQueue = review.data?.next_question_id;
    if (nextInQueue) {
      goTo(nextInQueue);
    } else {
      toast.success("Queue done: every question of the job is decided.");
      navigate(`/transfers/${transferId}`);
    }
  };

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
          {transferId ? (
            <span className="flex items-center gap-3">
              <Link to={`/transfers/${transferId}`} className="text-rust hover:underline">
                ← Queue
              </Link>
              {review.data?.next_question_id ? (
                <button
                  type="button"
                  className="text-rust hover:underline"
                  onClick={() => goTo(review.data!.next_question_id!)}
                  data-testid="skip-question"
                >
                  Skip →
                </button>
              ) : null}
            </span>
          ) : configurationId ? (
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

      {review.data && review.data.reference.length > 0 ? (
        <details className="mb-4 rounded-lg border border-line bg-paper-raised p-3 text-sm" open>
          <summary className="cursor-pointer text-xs text-ink-muted">
            Confirmed in the source configuration ({review.data.reference.length})
          </summary>
          <ul className="mt-2 space-y-2" data-testid="reference-chunks">
            {review.data.reference.map((chunk) => (
              <li key={chunk.chunk_id} className="whitespace-pre-wrap text-xs leading-5">
                <Badge>{chunk.relevance}</Badge> {chunk.text}
              </li>
            ))}
          </ul>
        </details>
      ) : null}

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
      ) : question.data && evidence.data && (!transferId || review.data) ? (
        <Workbench
          // Remounted per question and configuration, so the draft starts from what is saved.
          key={`${questionId}:${configurationId}:${transferId}`}
          review={review.data}
          onDecided={transferId ? afterDecision : undefined}
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
  review,
  onDecided,
}: {
  review?: QuestionReviewRead;
  onDecided?: () => void;
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
  // In a review queue the pre-selected candidates start ticked, never confirmed.
  const [draft, setDraft] = useState<DraftChunk[]>(() =>
    review ? initialDraft(evidence, review.candidates) : draftFromEvidence(evidence),
  );
  const [pane, setPane] = useState<"candidates" | "document" | "search">(
    review ? "candidates" : "document",
  );
  const [candidateIndex, setCandidateIndex] = useState(0);
  const candidates = review?.candidates ?? [];
  const candidateById = new Map(candidates.map((candidate) => [candidate.chunk_id, candidate]));
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

  const pick = (chunk: Omit<DraftChunk, "relevance">, relevance: RelevanceGrade | null) =>
    setDraft((current) => setRelevance(current, chunk, relevance));

  const save = useMutation({
    mutationFn: (decision: EvidenceDecision) =>
      questionsApi.saveEvidence(
        question.id,
        evidencePayload(configurationId, decision, draft, annotator),
      ),
    onSuccess: async (result, decision) => {
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
      if (review) {
        await queryClient.invalidateQueries({
          queryKey: queryKeys.transfer(review.transfer_job_id),
        });
        if (decision !== "to_review") onDecided?.();
      }
    },
  });

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes(target.tagName)) return;
      if (review) {
        // Queue keys: decide and move on without the mouse.
        const decision =
          event.key === "Enter" ? "confirmed" : event.key === "n" ? "not_found" : null;
        if (decision) {
          event.preventDefault();
          if (!save.isPending && blockedReason(decision, draft, annotator) === null) {
            save.mutate(decision);
          }
          return;
        }
      }
      if (review && pane === "candidates") {
        if (event.key === "ArrowDown" || event.key === "j") {
          event.preventDefault();
          setCandidateIndex((index) => Math.min(index + 1, candidates.length - 1));
        } else if (event.key === "ArrowUp" || event.key === "k") {
          event.preventDefault();
          setCandidateIndex((index) => Math.max(index - 1, 0));
        } else if (event.key in RELEVANCE_KEYS && candidates[candidateIndex]) {
          event.preventDefault();
          pick(candidateChunk(candidates[candidateIndex]), RELEVANCE_KEYS[event.key]);
        }
        return;
      }
      if (!(event.key in RELEVANCE_KEYS) || !selectedId) return;
      const chunk = navigable.find((item) => item.id === selectedId);
      if (!chunk) return;
      event.preventDefault();
      mark(chunk, RELEVANCE_KEYS[event.key]);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
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
            {review ? (
              <>
                {" "}
                · <kbd>Enter</kbd> confirm &amp; next, <kbd>n</kbd> not found &amp; next
              </>
            ) : null}
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
          queueMode={Boolean(review)}
        />
      </aside>

      <div className="flex min-w-0 flex-col gap-2">
        {review ? (
          <div className="flex gap-2 text-sm" role="tablist">
            {(
              [
                ["candidates", `Candidates (${candidates.length})`],
                ["document", "Document"],
                ["search", "Search"],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                role="tab"
                aria-selected={pane === value}
                onClick={() => setPane(value)}
                className={`rounded-full border px-3 py-1 ${
                  pane === value ? "border-rust text-rust" : "border-line text-ink-muted"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        ) : null}
        {review && pane === "candidates" ? (
          <div className="flex h-[calc(100vh-14rem)] min-h-[28rem] flex-col overflow-hidden rounded-xl border border-line bg-paper">
            <CandidateList
              candidates={candidates}
              grades={grades}
              selectedIndex={candidateIndex}
              onSelect={setCandidateIndex}
              onMark={(candidate, relevance) => pick(candidateChunk(candidate), relevance)}
              onOpen={(candidate) => {
                onDocument(candidate.document_id);
                setSelectedId(candidate.chunk_id);
                setPane("document");
              }}
            />
          </div>
        ) : review && pane === "search" ? (
          <div className="flex h-[calc(100vh-14rem)] min-h-[28rem] flex-col overflow-hidden rounded-xl border border-line bg-paper">
            <ChunkSearch
              configurationId={configurationId}
              corpusId={originCorpusId}
              grades={grades}
              onMark={(hit, relevance) => pick(hit, relevance)}
              onOpen={(hit) => {
                onDocument(hit.document_id);
                setSelectedId(hit.chunk_id);
                setPane("document");
              }}
            />
          </div>
        ) : !activeDocumentId ? (
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
            renderChunkActions={(chunk) => {
              const candidate = candidateById.get(chunk.id);
              return (
                <span className="flex items-center gap-2">
                  {candidate ? (
                    <Badge tone={candidate.confidence === "high" ? "good" : "info"}>
                      {`#${candidate.rank} · ${formatScore(candidate.combined_score)}`}
                    </Badge>
                  ) : null}
                  <RelevanceToggle
                    ordinal={chunk.ordinal}
                    value={grades.get(chunk.id) ?? null}
                    onChange={(relevance) => mark(chunk, relevance)}
                  />
                </span>
              );
            }}
          />
        )}
      </div>
    </div>
  );
}
