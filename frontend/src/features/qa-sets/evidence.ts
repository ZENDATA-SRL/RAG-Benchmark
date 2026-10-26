import type {
  EvidenceRead,
  EvidenceStatus,
  EvidenceWrite,
  QuestionRead,
  RelevanceGrade,
} from "@/api/types";

/** A chunk picked as evidence, with enough context to list it without reloading it. */
export type DraftChunk = {
  chunk_id: string;
  relevance: RelevanceGrade;
  document_id: string;
  filename: string;
  ordinal: number;
  text: string;
};

export type EvidenceDecision = Exclude<EvidenceStatus, "not_reviewed">;

const STATUS_LABELS: Record<EvidenceStatus, string> = {
  not_reviewed: "not reviewed",
  to_review: "draft",
  confirmed: "confirmed",
  not_found: "not found",
};

const STATUS_TONES: Record<EvidenceStatus, "neutral" | "good" | "warn" | "bad"> = {
  not_reviewed: "neutral",
  to_review: "warn",
  confirmed: "good",
  not_found: "bad",
};

export function statusLabel(status: EvidenceStatus): string {
  return STATUS_LABELS[status];
}

export function statusTone(status: EvidenceStatus) {
  return STATUS_TONES[status];
}

/** The saved evidence as an editable draft, in reading order. */
export function draftFromEvidence(evidence: EvidenceRead | undefined): DraftChunk[] {
  return (evidence?.chunks ?? []).map((chunk) => ({
    chunk_id: chunk.chunk_id,
    relevance: chunk.relevance,
    document_id: chunk.document_id,
    filename: chunk.filename,
    ordinal: chunk.ordinal,
    text: chunk.text,
  }));
}

/**
 * Mark a chunk with a relevance grade, or take it out of the evidence with `null`.
 * Marking a chunk again with the grade it already has takes it out, so one key toggles.
 */
export function setRelevance(
  draft: DraftChunk[],
  chunk: Omit<DraftChunk, "relevance">,
  relevance: RelevanceGrade | null,
): DraftChunk[] {
  const current = draft.find((item) => item.chunk_id === chunk.chunk_id);
  const rest = draft.filter((item) => item.chunk_id !== chunk.chunk_id);
  if (relevance === null || current?.relevance === relevance) {
    return rest;
  }
  return sortDraft([...rest, { ...chunk, relevance }]);
}

function sortDraft(draft: DraftChunk[]): DraftChunk[] {
  return [...draft].sort(
    (a, b) =>
      a.filename.localeCompare(b.filename) ||
      a.document_id.localeCompare(b.document_id) ||
      a.ordinal - b.ordinal,
  );
}

/** Same chunks with the same grades, whatever the order. */
export function sameDraft(a: DraftChunk[], b: DraftChunk[]): boolean {
  if (a.length !== b.length) return false;
  const grades = new Map(a.map((item) => [item.chunk_id, item.relevance]));
  return b.every((item) => grades.get(item.chunk_id) === item.relevance);
}

/**
 * Why a decision cannot be saved yet, or `null` when it can. Mirrors the server rules so the
 * buttons explain themselves instead of failing with a 422.
 */
export function blockedReason(
  decision: EvidenceDecision,
  draft: DraftChunk[],
  annotator: string,
): string | null {
  if (decision === "confirmed" && draft.length === 0) {
    return "Pick at least one chunk to confirm.";
  }
  if (decision === "not_found" && draft.length > 0) {
    return "Clear the chunks to record that the evidence is not here.";
  }
  if (decision !== "to_review" && !annotator.trim()) {
    return "Write your name: a decision records who took it.";
  }
  return null;
}

export function evidencePayload(
  configurationId: string,
  decision: EvidenceDecision,
  draft: DraftChunk[],
  annotator: string,
): EvidenceWrite {
  return {
    chunking_configuration_id: configurationId,
    status: decision,
    annotator: annotator.trim() || null,
    chunks: draft.map((item) => ({ chunk_id: item.chunk_id, relevance: item.relevance })),
  };
}

/** Whether a question still waits for a decision under the chosen configuration. */
export function needsReview(question: QuestionRead): boolean {
  return (
    question.answerable &&
    (question.evidence_status === "not_reviewed" || question.evidence_status === "to_review")
  );
}

/** The next question to review after `currentId`, wrapping around; `null` when none is left. */
export function nextToReview(questions: QuestionRead[], currentId: string): string | null {
  const start = questions.findIndex((question) => question.id === currentId);
  for (let step = 1; step <= questions.length; step += 1) {
    const candidate = questions[(start + step) % questions.length];
    if (candidate.id !== currentId && needsReview(candidate)) {
      return candidate.id;
    }
  }
  return null;
}

export type StatusFilter = "all" | "needs_review" | "confirmed" | "not_found";

export function filterQuestions(questions: QuestionRead[], filter: StatusFilter): QuestionRead[] {
  if (filter === "all") return questions;
  if (filter === "needs_review") return questions.filter(needsReview);
  return questions.filter((question) => question.evidence_status === filter);
}

/** Which call saving a question makes: a frozen question can only be replaced, never edited. */
export function editorMode(question: QuestionRead | null): "create" | "edit" | "replace" {
  if (!question) return "create";
  return question.frozen ? "replace" : "edit";
}

export function sameIds(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((id) => b.includes(id));
}

const ANNOTATOR_KEY = "rag-bench.annotator";

/** The annotator's name is remembered per browser; storage may be unavailable. */
export function loadAnnotator(): string {
  try {
    return window.localStorage.getItem(ANNOTATOR_KEY) ?? "";
  } catch {
    return "";
  }
}

export function saveAnnotator(name: string): void {
  try {
    window.localStorage.setItem(ANNOTATOR_KEY, name);
  } catch {
    // Only a convenience: the name is typed again next time.
  }
}
