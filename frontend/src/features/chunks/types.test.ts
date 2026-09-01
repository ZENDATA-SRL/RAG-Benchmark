import { describe, expect, it } from "vitest";

import { coversPage, formatPageSpan, pageOf, pageSpanOf, type NavigableChunk } from "./types";

function chunk(metadata: Record<string, unknown>): NavigableChunk {
  return { id: "c1", ordinal: 1, text: "x", metadata };
}

describe("pageSpanOf", () => {
  it("reads an inclusive page_span that can cover several pages", () => {
    expect(pageSpanOf(chunk({ page: 3, page_span: [3, 5] }))).toEqual({ first: 3, last: 5 });
    expect(formatPageSpan({ first: 3, last: 5 })).toBe("pages 3–5");
    expect(coversPage(chunk({ page_span: [3, 5] }), 4)).toBe(true);
    expect(coversPage(chunk({ page_span: [3, 5] }), 6)).toBe(false);
  });

  it("falls back to page when page_span is missing", () => {
    expect(pageSpanOf(chunk({ page: 7 }))).toEqual({ first: 7, last: 7 });
    expect(pageOf(chunk({ page: 7 }))).toBe(7);
  });
});
