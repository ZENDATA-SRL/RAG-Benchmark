import type { CandidateRead, EvidenceRead, QueueState } from "@/api/types";

import { draftFromEvidence, type DraftChunk } from "../qa-sets/evidence";

/** The states of the queue, in the order the review goes through them. */
export const QUEUE_STATES: QueueState[] = [
  "preselected",
  "to_review",
  "no_candidates",
  "pending",
  "failed",
  "decided",
];

const LABELS: Record<QueueState, string> = {
  preselected: "pre-selected",
  to_review: "to choose",
  no_candidates: "no plausible candidate",
  pending: "ranking",
  failed: "failed",
  decided: "decided",
};

const TONES: Record<QueueState, "neutral" | "good" | "warn" | "bad" | "info"> = {
  preselected: "good",
  to_review: "info",
  no_candidates: "warn",
  pending: "neutral",
  failed: "bad",
  decided: "neutral",
};

export function queueLabel(state: QueueState): string {
  return LABELS[state];
}

export function queueTone(state: QueueState) {
  return TONES[state];
}

/** A candidate as a chunk the draft can hold. */
export function candidateChunk(candidate: CandidateRead): Omit<DraftChunk, "relevance"> {
  return {
    chunk_id: candidate.chunk_id,
    document_id: candidate.document_id,
    filename: candidate.filename,
    ordinal: candidate.ordinal,
    text: candidate.text,
  };
}

/**
 * What the reviewer starts from: the saved evidence when there is any, otherwise the
 * pre-selected candidates already ticked, with the grade the source suggests. Ticked is not
 * confirmed: nothing is written until the reviewer confirms.
 */
export function initialDraft(
  evidence: EvidenceRead,
  candidates: CandidateRead[] | undefined,
): DraftChunk[] {
  const saved = draftFromEvidence(evidence);
  if (saved.length > 0 || evidence.status === "confirmed" || evidence.status === "not_found") {
    return saved;
  }
  return (candidates ?? [])
    .filter((candidate) => candidate.preselected)
    .map((candidate) => ({
      ...candidateChunk(candidate),
      relevance: candidate.suggested_relevance ?? "sufficient",
    }));
}

/**
 * A chunk's text on one line of flowing words, for reading candidates side by side: some
 * extractions break a line after every word, which no one can scan. Display only; the
 * document view keeps the text as parsed.
 */
export function compactText(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

export function formatScore(score: number | null | undefined): string {
  return score === null || score === undefined ? "—" : score.toFixed(2);
}

/** The URL that reviews a question of a job, on the annotation page in queue mode. */
export function reviewUrl(
  qaSetId: string,
  questionId: string,
  transferId: string,
  configurationId: string,
): string {
  const params = new URLSearchParams({ configuration: configurationId, transfer: transferId });
  return `/qa-sets/${qaSetId}/questions/${questionId}/annotate?${params.toString()}`;
}
