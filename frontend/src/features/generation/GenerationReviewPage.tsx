import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { generationApi, qaSetsApi } from "@/api/resources";
import type { GeneratedKind, ProposalDecision, ProposalReviewRead } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { TableSkeleton } from "@/components/ui/Skeleton";
import { queryKeys } from "@/lib/queryClient";

import { PdfPane } from "../chunks/PdfPane";
import { loadAnnotator, saveAnnotator } from "../qa-sets/evidence";
import { RelevanceToggle } from "../qa-sets/RelevanceToggle";
import { ChunkSearch } from "../transfers/ChunkSearch";
import {
  acceptPayload,
  blockedReason,
  type DraftChunk,
  draftFrom,
  KIND_LABELS,
  kindOf,
  reviewUrl,
  type ReviewDraft,
  splitOnQuote,
  withChunk,
} from "./generation";

const INPUT = "w-full rounded-md border border-line bg-paper-raised px-2 py-1 text-sm";

function ChunkText({ text, quote }: { text: string; quote: string | null }) {
  const parts = splitOnQuote(text, quote);
  if (!parts) {
    return (
      <>
        <p className="whitespace-pre-wrap text-ink-muted">{text}</p>
        {quote ? (
          <p className="mt-1 text-xs">
            <span className="text-ink-muted">Quoted: </span>
            <span className="underline decoration-rust">{quote}</span>
          </p>
        ) : null}
      </>
    );
  }
  return (
    <p className="whitespace-pre-wrap text-ink-muted">
      {parts.before}
      <mark className="bg-transparent text-ink underline decoration-rust decoration-2">
        {parts.match}
      </mark>
      {parts.after}
    </p>
  );
}

/**
 * A generated question opened for review: question and answer editable, the cited chunks
 * with the quoted passage underlined, chunks to remove or add, then accept or reject.
 * Keys: `a` accepts, `r` rejects, `n` skips to the next one.
 */
export function GenerationReviewPage() {
  const { jobId = "", proposalId = "" } = useParams();
  const [params] = useSearchParams();
  const kind = (params.get("kind") ?? "") as GeneratedKind | "";
  const proposal = useQuery({
    queryKey: queryKeys.proposal(proposalId, kind),
    queryFn: () => generationApi.proposal(proposalId, kind || undefined),
  });

  if (proposal.isLoading) return <TableSkeleton />;
  if (!proposal.data) {
    return <EmptyState title="Question not found" body="It may have been removed." />;
  }
  // Keyed on the proposal, so moving to the next one starts from a fresh draft.
  return <Review key={proposal.data.id} jobId={jobId} kind={kind} review={proposal.data} />;
}

function Review({
  jobId,
  kind,
  review,
}: {
  jobId: string;
  kind: GeneratedKind | "";
  review: ProposalReviewRead;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<ReviewDraft>(() => draftFrom(review));
  const [annotator, setAnnotator] = useState(loadAnnotator);
  const [selected, setSelected] = useState<DraftChunk | null>(draft.chunks[0] ?? null);
  const [page, setPage] = useState(draft.chunks[0]?.page ?? 1);
  const [pane, setPane] = useState<"document" | "search">("document");
  const pending = review.status === "pending";

  const qaSet = useQuery({
    queryKey: queryKeys.qaSet(review.qa_set_id, ""),
    queryFn: () => qaSetsApi.get(review.qa_set_id),
    meta: { silent: true },
  });

  const next = (decision: ProposalDecision | null) => {
    const target = decision ? decision.next_proposal_id : review.next_proposal_id;
    navigate(target ? reviewUrl(jobId, target, kind) : `/generation-jobs/${jobId}`);
  };
  const decided = async (decision: ProposalDecision) => {
    saveAnnotator(annotator);
    await queryClient.invalidateQueries({ queryKey: queryKeys.generation(jobId) });
    await queryClient.invalidateQueries({ queryKey: queryKeys.generationProposals(jobId) });
    await queryClient.invalidateQueries({ queryKey: queryKeys.qaSetScope(review.qa_set_id) });
    next(decision);
  };
  const accept = useMutation({
    mutationFn: () => generationApi.accept(review.id, acceptPayload(draft, annotator)),
    onSuccess: decided,
  });
  const reject = useMutation({
    mutationFn: () => generationApi.reject(review.id, annotator),
    onSuccess: decided,
  });
  const blocked = blockedReason(draft, annotator);
  const busy = accept.isPending || reject.isPending;

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes(target.tagName)) return;
      if (event.key === "n") {
        event.preventDefault();
        next(null);
      } else if (pending && !busy && event.key === "a" && blocked === null) {
        event.preventDefault();
        accept.mutate();
      } else if (pending && !busy && event.key === "r") {
        event.preventDefault();
        reject.mutate();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const show = (chunk: DraftChunk) => {
    setSelected(chunk);
    setPage(chunk.page ?? 1);
    setPane("document");
  };
  const grades = new Map(draft.chunks.map((chunk) => [chunk.chunk_id, chunk.relevance]));
  const currentKind = kindOf(draft.chunks);

  return (
    <div>
      <p className="mb-2 text-sm">
        <Link to={`/generation-jobs/${jobId}`} className="text-rust hover:underline">
          Generated questions
        </Link>
        <span className="text-ink-muted"> / review</span>
      </p>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <section className="space-y-3" data-testid="proposal-review">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="info">{KIND_LABELS[currentKind]}</Badge>
            {currentKind !== review.kind ? (
              <span className="text-xs text-ink-muted">proposed as {KIND_LABELS[review.kind]}</span>
            ) : null}
            <Badge
              tone={
                review.status === "accepted"
                  ? "good"
                  : review.status === "rejected"
                    ? "bad"
                    : "neutral"
              }
            >
              {review.status}
            </Badge>
            {review.trace_url ? (
              <a
                href={review.trace_url}
                target="_blank"
                rel="noreferrer"
                className="ml-auto text-xs text-rust hover:underline"
              >
                Trace
              </a>
            ) : null}
          </div>
          <label className="block text-xs">
            <span className="mb-1 block text-ink-muted">Question</span>
            <textarea
              value={draft.text}
              onChange={(event) => setDraft({ ...draft, text: event.target.value })}
              rows={2}
              disabled={!pending}
              className={INPUT}
              aria-label="Question"
            />
          </label>
          <label className="block text-xs">
            <span className="mb-1 block text-ink-muted">Expected answer</span>
            <textarea
              value={draft.answer}
              onChange={(event) => setDraft({ ...draft, answer: event.target.value })}
              rows={3}
              disabled={!pending}
              className={INPUT}
              aria-label="Expected answer"
            />
          </label>

          <div>
            <p className="mb-1 text-xs text-ink-muted">Evidence chunks</p>
            <ul className="space-y-2" data-testid="proposal-chunks">
              {draft.chunks.map((chunk) => (
                <li
                  key={chunk.chunk_id}
                  className={`rounded-lg border p-3 text-sm ${
                    selected?.chunk_id === chunk.chunk_id ? "border-rust" : "border-line"
                  }`}
                >
                  <div className="mb-1 flex items-center gap-2 text-xs">
                    <button
                      type="button"
                      className="font-mono text-rust hover:underline"
                      onClick={() => show(chunk)}
                    >
                      {chunk.filename} #{chunk.ordinal}
                      {chunk.page ? ` · p. ${chunk.page}` : ""}
                    </button>
                    {pending ? (
                      <span className="ml-auto">
                        <RelevanceToggle
                          ordinal={chunk.ordinal}
                          value={chunk.relevance}
                          onChange={(relevance) => setDraft(withChunk(draft, chunk, relevance))}
                        />
                      </span>
                    ) : (
                      <span className="ml-auto text-ink-muted">{chunk.relevance}</span>
                    )}
                  </div>
                  <ChunkText text={chunk.text} quote={chunk.quote} />
                </li>
              ))}
            </ul>
          </div>

          {pending ? (
            <div className="flex flex-wrap items-center gap-2">
              <input
                value={annotator}
                onChange={(event) => setAnnotator(event.target.value)}
                placeholder="Your name"
                aria-label="Annotator"
                className="w-40 rounded-md border border-line bg-paper-raised px-2 py-1 text-sm"
              />
              <Button
                onClick={() => accept.mutate()}
                disabled={blocked !== null || busy}
                title={blocked ?? "Accept (a)"}
              >
                Accept
              </Button>
              <Button
                variant="secondary"
                onClick={() => reject.mutate()}
                disabled={busy}
                title="Reject (r)"
              >
                Reject
              </Button>
              <Button variant="secondary" onClick={() => next(null)} title="Next (n)">
                Next
              </Button>
              {blocked ? <span className="text-xs text-ink-muted">{blocked}</span> : null}
            </div>
          ) : (
            <p className="text-xs text-ink-muted">
              {review.status} by {review.reviewed_by ?? "someone"}
              {review.accepted_question_id ? (
                <>
                  {" · "}
                  <Link
                    to={`/qa-sets/${review.qa_set_id}/questions/${review.accepted_question_id}/annotate?configuration=${review.chunking_configuration_id}`}
                    className="text-rust hover:underline"
                  >
                    open the question
                  </Link>
                </>
              ) : null}
            </p>
          )}
          <p className="text-[11px] text-ink-muted">
            Keys: a accept · r reject · n next. Accepting adds the question to the set with
            confirmed evidence and the tags generated, generated:{currentKind}.
          </p>
        </section>

        <section className="flex h-[calc(100vh-11rem)] min-h-[30rem] flex-col overflow-hidden rounded-xl border border-line bg-paper-raised">
          <div className="flex gap-2 border-b border-line px-3 py-2 text-xs">
            <button
              type="button"
              onClick={() => setPane("document")}
              className={pane === "document" ? "text-rust" : "text-ink-muted"}
            >
              Document
            </button>
            {pending ? (
              <button
                type="button"
                onClick={() => setPane("search")}
                className={pane === "search" ? "text-rust" : "text-ink-muted"}
              >
                Add chunks
              </button>
            ) : null}
          </div>
          <div className="min-h-0 flex-1">
            {pane === "search" ? (
              <ChunkSearch
                configurationId={review.chunking_configuration_id}
                corpusId={qaSet.data?.origin_corpus_id ?? null}
                grades={grades}
                onMark={(hit, relevance) =>
                  setDraft(
                    withChunk(
                      draft,
                      {
                        chunk_id: hit.chunk_id,
                        document_id: hit.document_id,
                        filename: hit.filename,
                        ordinal: hit.ordinal,
                        page: hit.page ?? null,
                        text: hit.text,
                        quote: null,
                      },
                      relevance,
                    ),
                  )
                }
                onOpen={(hit) =>
                  show({
                    chunk_id: hit.chunk_id,
                    document_id: hit.document_id,
                    filename: hit.filename,
                    ordinal: hit.ordinal,
                    page: hit.page ?? null,
                    text: hit.text,
                    quote: null,
                    relevance: "supporting",
                  })
                }
              />
            ) : selected ? (
              <PdfPane documentId={selected.document_id} page={page} onPageChange={setPage} />
            ) : (
              <p className="p-3 text-xs text-ink-muted">Choose a chunk to see its page.</p>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
