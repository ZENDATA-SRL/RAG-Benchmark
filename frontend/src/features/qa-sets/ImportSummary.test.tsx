import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { ImportSummaryRead } from "@/api/types";

import { importCounts, skippedCount } from "./importCounts";
import { ImportSummary } from "./ImportSummary";

const SUMMARY: ImportSummaryRead = {
  qa_set_id: "qa-1",
  total_rows: 6,
  imported: [{ row: 1, question_id: "q1", text: "Q1", gold_documents: [] }],
  existing: [{ row: 2, question_id: "q2", text: "Q2", gold_documents: [] }],
  unresolved: [{ row: 3, question: "Q3", files: ["missing.pdf"] }],
  ambiguous: [
    {
      row: 4,
      question: "Q4",
      files: [
        {
          file: "dup.pdf",
          candidates: [
            { document_id: "d1", filename: "dup.pdf", content_hash: "aaaaaaaa11" },
            { document_id: "d2", filename: "dup.pdf", content_hash: "bbbbbbbb22" },
          ],
        },
      ],
    },
  ],
  invalid: [
    { row: 5, question: "", reason: "empty question" },
    { row: 6, question: "Q6", reason: "bad answerable" },
  ],
};

afterEach(cleanup);

describe("ImportSummary", () => {
  it("counts every outcome", () => {
    expect(importCounts(SUMMARY)).toEqual({
      imported: 1,
      existing: 1,
      unresolved: 1,
      ambiguous: 1,
      invalid: 2,
    });
    expect(skippedCount(SUMMARY)).toBe(4);
  });

  it("lists the offending rows instead of hiding them", () => {
    render(<ImportSummary summary={SUMMARY} />);

    expect(screen.getByText("1 imported")).toBeInTheDocument();
    expect(screen.getByText("2 invalid")).toBeInTheDocument();
    expect(screen.getByTestId("import-unresolved")).toHaveTextContent("missing.pdf");
    expect(screen.getByTestId("import-ambiguous")).toHaveTextContent("dup.pdf: 2 candidates");
    expect(screen.getByTestId("import-invalid")).toHaveTextContent("bad answerable");
  });
});
