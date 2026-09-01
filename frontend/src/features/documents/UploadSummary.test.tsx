import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { UploadSummary } from "./UploadSummary";

const RESULTS = [
  { filename: "a.pdf", outcome: "imported" as const, document_id: "11111111-1111-1111-1111-111111111111", error_reason: null },
  { filename: "b.pdf", outcome: "imported" as const, document_id: "22222222-2222-2222-2222-222222222222", error_reason: null },
  { filename: "c.pdf", outcome: "imported" as const, document_id: "33333333-3333-3333-3333-333333333333", error_reason: null },
  { filename: "notes.txt", outcome: "skipped_unsupported" as const, document_id: null, error_reason: "unsupported extension" },
  {
    filename: "copy.pdf",
    outcome: "skipped_duplicate" as const,
    document_id: "11111111-1111-1111-1111-111111111111",
    error_reason: null,
  },
];

describe("UploadSummary", () => {
  it("separates the four outcomes and links a duplicate to the existing document", () => {
    render(
      <MemoryRouter>
        <UploadSummary results={RESULTS} corpusId="corpus-1" />
      </MemoryRouter>,
    );

    expect(screen.getByText("3 imported")).toBeInTheDocument();
    expect(screen.getByText("1 duplicates")).toBeInTheDocument();
    expect(screen.getByText("1 unsupported")).toBeInTheDocument();
    expect(screen.getByText("0 failed")).toBeInTheDocument();
    expect(screen.getByText("Already known. Not an error — the existing document was reused.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "open existing document" })).toHaveAttribute(
      "href",
      "/corpora/corpus-1?document=11111111-1111-1111-1111-111111111111",
    );
    expect(screen.getByText("notes.txt")).toBeInTheDocument();
  });
});
