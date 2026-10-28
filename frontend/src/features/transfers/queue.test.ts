import { describe, expect, it } from "vitest";

import type { CandidateRead, EvidenceRead } from "@/api/types";

import { compactText, formatScore, initialDraft, queueLabel, reviewUrl } from "./queue";

function candidate(id: string, overrides: Partial<CandidateRead> = {}): CandidateRead {
  return {
    chunk_id: id,
    document_id: "doc",
    filename: "Capitolato.pdf",
    ordinal: 3,
    page: 2,
    text: `text ${id}`,
    rank: 1,
    combined_score: 0.8,
    semantic_score: 0.7,
    lexical_score: 0.96,
    positional_score: 1,
    confidence: "high",
    preselected: false,
    suggested_relevance: null,
    ...overrides,
  };
}

function evidence(overrides: Partial<EvidenceRead> = {}): EvidenceRead {
  return {
    question_id: "q",
    chunking_configuration_id: "cfg",
    status: "not_reviewed",
    chunks: [],
    ...overrides,
  } as EvidenceRead;
}

describe("initialDraft", () => {
  const candidates = [
    candidate("a", { preselected: true, suggested_relevance: "supporting" }),
    candidate("b", { preselected: true }),
    candidate("c"),
  ];

  it("ticks the pre-selected candidates when nothing is saved", () => {
    expect(initialDraft(evidence(), candidates).map((c) => [c.chunk_id, c.relevance])).toEqual([
      ["a", "supporting"],
      ["b", "sufficient"],
    ]);
  });

  it("keeps a decision already taken", () => {
    expect(initialDraft(evidence({ status: "not_found" }), candidates)).toEqual([]);
    const saved = evidence({
      status: "to_review",
      chunks: [
        {
          chunk_id: "c",
          relevance: "sufficient",
          graded_relevance: null,
          document_id: "doc",
          filename: "Capitolato.pdf",
          ordinal: 3,
          text: "text c",
        },
      ],
    } as Partial<EvidenceRead>);
    expect(initialDraft(saved, candidates).map((c) => c.chunk_id)).toEqual(["c"]);
  });
});

describe("helpers", () => {
  it("flows a text broken after every word", () => {
    expect(compactText("la\n\nsessione  \n prosegue ")).toBe("la sessione prosegue");
  });

  it("formats scores and labels", () => {
    expect(formatScore(0.8234)).toBe("0.82");
    expect(formatScore(null)).toBe("—");
    expect(queueLabel("no_candidates")).toBe("no plausible candidate");
  });

  it("builds the review URL in queue mode", () => {
    expect(reviewUrl("set", "q", "job", "cfg")).toBe(
      "/qa-sets/set/questions/q/annotate?configuration=cfg&transfer=job",
    );
  });
});
