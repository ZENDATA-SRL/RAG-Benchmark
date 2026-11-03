import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { generationApi } from "@/api/resources";

import { GenerationReviewPage } from "./GenerationReviewPage";

const chunk = (id: string, ordinal: number, text: string, quote: string) => ({
  chunk_id: id,
  document_id: "doc-1",
  filename: "capitolato.pdf",
  ordinal,
  page: ordinal + 1,
  text,
  quote,
  relevance: "supporting" as const,
  rank: ordinal + 1,
});

const proposal = {
  id: "p1",
  generation_job_id: "job-1",
  kind: "multi" as const,
  text: "Quali penali e orari prevede il capitolato?",
  answer: "1 per mille; 9-18.",
  status: "pending" as const,
  accepted_question_id: null,
  reviewed_by: null,
  reviewed_at: null,
  created_at: "2026-11-02T10:00:00Z",
  chunks: [
    chunk(
      "c1",
      1,
      "Premessa. La penale è pari\nall’1 per mille.",
      "La penale è pari all'1 per mille",
    ),
    chunk("c2", 2, "Assistenza dalle nove alle diciotto.", "dalle nove alle diciotto"),
  ],
  qa_set_id: "set-1",
  chunking_configuration_id: "conf-1",
  phase: "document" as const,
  trace_url: null,
  next_proposal_id: "p2",
};

vi.mock("@/api/resources", () => ({
  generationApi: {
    proposal: vi.fn(() => Promise.resolve(proposal)),
    accept: vi.fn(() => Promise.resolve({ proposal, question_id: "q1", next_proposal_id: "p2" })),
    reject: vi.fn(),
  },
  qaSetsApi: { get: () => Promise.resolve({ origin_corpus_id: "corpus-1" }) },
  inspectionApi: { search: vi.fn() },
}));
vi.mock("../chunks/PdfPane", () => ({
  PdfPane: ({ page }: { page: number }) => <div data-testid="pdf">page {page}</div>,
}));

afterEach(cleanup);

function renderPage() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={["/generation-jobs/job-1/review/p1"]}>
        <Routes>
          <Route
            path="/generation-jobs/:jobId/review/:proposalId"
            element={<GenerationReviewPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("GenerationReviewPage", () => {
  it("underlines the quotes and opens the page of the first chunk", async () => {
    renderPage();
    const marks = await screen.findAllByText(/La penale è pari|dalle nove alle diciotto/, {
      selector: "mark",
    });
    expect(marks).toHaveLength(2);
    expect(screen.getByTestId("pdf")).toHaveTextContent("page 2");
    expect(screen.getByText("multi-chunk")).toBeInTheDocument();
  });

  it("accepts the corrected question with the chunks kept, by keyboard", async () => {
    const user = userEvent.setup();
    renderPage();
    const question = await screen.findByRole("textbox", { name: "Question" });

    await user.clear(question);
    await user.type(question, "Qual è la penale giornaliera?");
    // Removing the second chunk leaves a single chunk question, sufficient on its own.
    await user.click(screen.getByRole("button", { name: "Mark chunk 2 as supporting" }));
    await user.click(screen.getByRole("button", { name: "Mark chunk 1 as sufficient" }));
    expect(screen.getByText("single chunk")).toBeInTheDocument();
    await user.type(screen.getByRole("textbox", { name: "Annotator" }), "anna");
    (document.activeElement as HTMLElement).blur();
    await user.keyboard("a");

    await waitFor(() =>
      expect(generationApi.accept).toHaveBeenCalledWith("p1", {
        text: "Qual è la penale giornaliera?",
        answer: "1 per mille; 9-18.",
        chunks: [{ chunk_id: "c1", relevance: "sufficient" }],
        annotator: "anna",
      }),
    );
  });
});
