import type {
  GeneratedKind,
  GenerationRead,
  ProposalAccept,
  ProposalChunkRead,
  RelevanceGrade,
} from "@/api/types";

export const KIND_LABELS: Record<GeneratedKind, string> = {
  single: "single chunk",
  multi: "multi-chunk",
  cross: "cross-document",
};

export const DISCARD_LABELS: Record<string, string> = {
  unknown_chunk: "unknown chunk",
  empty_field: "empty field",
  quote_not_in_chunk: "quote not in the chunk",
  outside_document: "outside the document",
  single_document: "one document only",
  too_many_documents: "too many documents",
  too_many_chunks: "too many chunks",
  duplicate: "duplicate",
};

export const END_REASON_LABELS: Record<string, string> = {
  target_reached: "target reached",
  agent_finished: "agent finished",
  agent_stopped: "agent stopped",
  max_steps: "step limit",
  invalid_output: "invalid output",
};

/** The review of a proposal; with a kind, "next" stays within that kind. */
export function reviewUrl(jobId: string, proposalId: string, kind?: GeneratedKind | ""): string {
  return `/generation-jobs/${jobId}/review/${proposalId}${kind ? `?kind=${kind}` : ""}`;
}

export function isActive(job: GenerationRead | undefined): boolean {
  return !job || job.status === "pending" || job.status === "running";
}

/** A chunk of the evidence as the reviewer edits it: proposed, or added from a search. */
export type DraftChunk = {
  chunk_id: string;
  document_id: string;
  filename: string;
  ordinal: number;
  page: number | null;
  text: string;
  quote: string | null;
  relevance: RelevanceGrade;
};

export type ReviewDraft = {
  text: string;
  answer: string;
  chunks: DraftChunk[];
};

export function draftFrom(proposal: {
  text: string;
  answer: string;
  chunks: ProposalChunkRead[];
}): ReviewDraft {
  return {
    text: proposal.text,
    answer: proposal.answer,
    chunks: proposal.chunks.map((chunk) => ({
      chunk_id: chunk.chunk_id,
      document_id: chunk.document_id,
      filename: chunk.filename,
      ordinal: chunk.ordinal,
      page: chunk.page ?? null,
      text: chunk.text,
      quote: chunk.quote,
      relevance: chunk.relevance,
    })),
  };
}

/** The kind the question will be tagged with, from the chunks kept, as the server reads it. */
export function kindOf(chunks: Pick<DraftChunk, "document_id">[]): GeneratedKind {
  if (new Set(chunks.map((chunk) => chunk.document_id)).size > 1) return "cross";
  return chunks.length > 1 ? "multi" : "single";
}

/** Why the draft cannot be accepted yet, or `null` when it can. */
export function blockedReason(draft: ReviewDraft, annotator: string): string | null {
  if (!draft.text.trim()) return "The question is empty.";
  if (!draft.answer.trim()) return "The answer is empty.";
  if (draft.chunks.length === 0) return "Keep at least one chunk.";
  if (!annotator.trim()) return "Type your name to record the decision.";
  return null;
}

export function acceptPayload(draft: ReviewDraft, annotator: string): ProposalAccept {
  return {
    text: draft.text.trim(),
    answer: draft.answer.trim(),
    chunks: draft.chunks.map((chunk) => ({
      chunk_id: chunk.chunk_id,
      relevance: chunk.relevance,
    })),
    annotator: annotator.trim(),
  };
}

/** Set, change or remove (with `null`) the grade of a chunk, adding it if it is new. */
export function withChunk(
  draft: ReviewDraft,
  chunk: Omit<DraftChunk, "relevance">,
  relevance: RelevanceGrade | null,
): ReviewDraft {
  const others = draft.chunks.filter((item) => item.chunk_id !== chunk.chunk_id);
  if (relevance === null) return { ...draft, chunks: others };
  const existing = draft.chunks.find((item) => item.chunk_id === chunk.chunk_id);
  const next = { ...(existing ?? chunk), relevance };
  return {
    ...draft,
    chunks: existing
      ? draft.chunks.map((item) => (item.chunk_id === chunk.chunk_id ? next : item))
      : [...draft.chunks, next],
  };
}

const QUOTE_CHARS = /['’‘`]/g;

/**
 * The chunk text split around the quote, so the passage the agent cited can be underlined.
 *
 * Words are matched in order, ignoring case, whitespace and the kind of apostrophe: the
 * parser breaks lines where the agent did not. A quote that cannot be found leaves the text
 * whole, and the quote is shown on its own.
 */
export function splitOnQuote(
  text: string,
  quote: string | null,
): { before: string; match: string; after: string } | null {
  const words = (quote ?? "").split(/\s+/).filter(Boolean);
  if (words.length === 0) return null;
  const pattern = words
    .map((word) => word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(QUOTE_CHARS, "['’‘`]"))
    .join("\\s+");
  const found = new RegExp(pattern, "i").exec(text);
  if (!found) return null;
  return {
    before: text.slice(0, found.index),
    match: found[0],
    after: text.slice(found.index + found[0].length),
  };
}
