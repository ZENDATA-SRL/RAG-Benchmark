import { describe, expect, it } from "vitest";

import {
  acceptPayload,
  blockedReason,
  type DraftChunk,
  kindOf,
  type ReviewDraft,
  splitOnQuote,
  withChunk,
} from "./generation";

const chunk = (id: string, document = "d1"): DraftChunk => ({
  chunk_id: id,
  document_id: document,
  filename: `${document}.pdf`,
  ordinal: 0,
  page: 1,
  text: "text",
  quote: null,
  relevance: "sufficient",
});

const draft = (chunks: DraftChunk[]): ReviewDraft => ({
  text: " Quanto costa? ",
  answer: "Poco.",
  chunks,
});

describe("generated question review", () => {
  it("reads the kind from the documents of the chunks kept", () => {
    expect(kindOf([chunk("a")])).toBe("single");
    expect(kindOf([chunk("a"), chunk("b")])).toBe("multi");
    expect(kindOf([chunk("a"), chunk("b", "d2")])).toBe("cross");
  });

  it("adds, regrades and removes chunks", () => {
    const start = draft([chunk("a")]);
    const added = withChunk(start, chunk("b"), "supporting");
    expect(added.chunks.map((item) => [item.chunk_id, item.relevance])).toEqual([
      ["a", "sufficient"],
      ["b", "supporting"],
    ]);
    const regraded = withChunk(added, chunk("a"), "supporting");
    expect(regraded.chunks[0].relevance).toBe("supporting");
    expect(withChunk(regraded, chunk("a"), null).chunks.map((item) => item.chunk_id)).toEqual([
      "b",
    ]);
  });

  it("blocks an accept without chunks or annotator and trims the payload", () => {
    expect(blockedReason(draft([]), "anna")).toMatch(/chunk/);
    expect(blockedReason(draft([chunk("a")]), " ")).toMatch(/name/);
    expect(blockedReason(draft([chunk("a")]), "anna")).toBeNull();
    expect(acceptPayload(draft([chunk("a")]), " anna ")).toEqual({
      text: "Quanto costa?",
      answer: "Poco.",
      chunks: [{ chunk_id: "a", relevance: "sufficient" }],
      annotator: "anna",
    });
  });

  it("finds the quote across line breaks and apostrophes", () => {
    const text = "Premessa. La penale è pari\nall’1 per mille. Fine.";
    expect(splitOnQuote(text, "la penale è pari all'1 per mille")).toEqual({
      before: "Premessa. ",
      match: "La penale è pari\nall’1 per mille",
      after: ". Fine.",
    });
    expect(splitOnQuote(text, "non c'è")).toBeNull();
    expect(splitOnQuote(text, null)).toBeNull();
  });
});
