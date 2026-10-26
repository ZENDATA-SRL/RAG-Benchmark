import { describe, expect, it } from "vitest";

import type { QuestionRead } from "@/api/types";

import {
  blockedReason,
  editorMode,
  evidencePayload,
  filterQuestions,
  nextToReview,
  sameDraft,
  setRelevance,
  type DraftChunk,
} from "./evidence";

function chunk(id: string, filename: string, ordinal: number): Omit<DraftChunk, "relevance"> {
  return { chunk_id: id, document_id: `doc-${filename}`, filename, ordinal, text: id };
}

function question(id: string, overrides: Partial<QuestionRead> = {}): QuestionRead {
  return {
    id,
    qa_set_id: "set",
    text: id,
    tags: [],
    answerable: true,
    gold_documents: [],
    expected_answers: [],
    frozen: false,
    replaced_by_question_id: null,
    evidence_status: "not_reviewed",
    ...overrides,
  };
}

describe("setRelevance", () => {
  it("adds chunks in reading order and toggles a grade off", () => {
    let draft = setRelevance([], chunk("b2", "b.pdf", 2), "sufficient");
    draft = setRelevance(draft, chunk("a7", "a.pdf", 7), "supporting");
    draft = setRelevance(draft, chunk("b1", "b.pdf", 1), "supporting");
    expect(draft.map((item) => item.chunk_id)).toEqual(["a7", "b1", "b2"]);

    draft = setRelevance(draft, chunk("b1", "b.pdf", 1), "sufficient");
    expect(draft.find((item) => item.chunk_id === "b1")?.relevance).toBe("sufficient");

    draft = setRelevance(draft, chunk("b1", "b.pdf", 1), "sufficient");
    expect(draft.map((item) => item.chunk_id)).toEqual(["a7", "b2"]);

    draft = setRelevance(draft, chunk("a7", "a.pdf", 7), null);
    expect(draft.map((item) => item.chunk_id)).toEqual(["b2"]);
  });
});

describe("sameDraft", () => {
  it("compares chunks and grades, not order", () => {
    const a = setRelevance(
      setRelevance([], chunk("x", "a.pdf", 1), "sufficient"),
      chunk("y", "a.pdf", 2),
      "supporting",
    );
    const reversed = [...a].reverse();
    expect(sameDraft(a, reversed)).toBe(true);
    expect(sameDraft(a, setRelevance(a, chunk("y", "a.pdf", 2), "sufficient"))).toBe(false);
  });
});

describe("blockedReason", () => {
  const picked = setRelevance([], chunk("x", "a.pdf", 1), "sufficient");

  it("mirrors the server rules of each decision", () => {
    expect(blockedReason("confirmed", [], "anna")).toMatch(/at least one chunk/);
    expect(blockedReason("not_found", picked, "anna")).toMatch(/Clear the chunks/);
    expect(blockedReason("confirmed", picked, "  ")).toMatch(/name/);
    expect(blockedReason("to_review", [], "")).toBeNull();
    expect(blockedReason("confirmed", picked, "anna")).toBeNull();
    expect(blockedReason("not_found", [], "anna")).toBeNull();
  });

  it("builds the payload the API expects", () => {
    expect(evidencePayload("cfg", "confirmed", picked, " anna ")).toEqual({
      chunking_configuration_id: "cfg",
      status: "confirmed",
      annotator: "anna",
      chunks: [{ chunk_id: "x", relevance: "sufficient" }],
    });
    expect(evidencePayload("cfg", "to_review", [], "").annotator).toBeNull();
  });
});

describe("nextToReview", () => {
  const questions = [
    question("q1", { evidence_status: "confirmed" }),
    question("q2"),
    question("q3", { answerable: false }),
    question("q4", { evidence_status: "to_review" }),
  ];

  it("finds the next question waiting for a decision, wrapping around", () => {
    expect(nextToReview(questions, "q2")).toBe("q4");
    expect(nextToReview(questions, "q4")).toBe("q2");
    expect(nextToReview(questions, "q1")).toBe("q2");
  });

  it("returns null when nothing else waits", () => {
    expect(nextToReview([question("q1")], "q1")).toBeNull();
  });

  it("filters by status", () => {
    expect(filterQuestions(questions, "needs_review").map((q) => q.id)).toEqual(["q2", "q4"]);
    expect(filterQuestions(questions, "confirmed").map((q) => q.id)).toEqual(["q1"]);
    expect(filterQuestions(questions, "all")).toHaveLength(4);
  });
});

describe("editorMode", () => {
  it("replaces a frozen question instead of editing it", () => {
    expect(editorMode(null)).toBe("create");
    expect(editorMode(question("q"))).toBe("edit");
    expect(editorMode(question("q", { frozen: true }))).toBe("replace");
  });
});
