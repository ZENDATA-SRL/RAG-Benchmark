import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { generationApi } from "@/api/resources";

import { GenerationDialog } from "./GenerationDialog";

const documents = [
  { document_id: "d-1", filename: "capitolato.pdf", materialised: true, excluded: false },
  { document_id: "d-2", filename: "contratto.pdf", materialised: true, excluded: false },
  { document_id: "d-3", filename: "allegato.pdf", materialised: true, excluded: false },
];
const numbers = {
  documents: 3,
  document_units: 3,
  cross_units: 0,
  max_steps: 40,
  max_model_calls: 120,
  target_questions: 9,
};

vi.mock("@/api/resources", () => ({
  generationApi: {
    estimate: vi.fn(() => Promise.resolve({ estimate: numbers, excluded: [], documents })),
    create: vi.fn(() => Promise.resolve({ id: "job-1", excluded: [] })),
  },
  configurationsApi: {
    list: () => Promise.resolve({ items: [{ id: "conf-1", name: "fixed 512" }] }),
  },
}));

afterEach(cleanup);

describe("GenerationDialog", () => {
  it("reads only the documents ticked", async () => {
    const user = userEvent.setup();
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <GenerationDialog qaSetId="set-1" configurationId="conf-1" onClose={() => {}} />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await screen.findByText("contratto.pdf");

    await user.click(screen.getByRole("radio", { name: "only the ones I tick" }));
    expect(screen.getByText(/Tick the documents to read/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start" })).toBeDisabled();

    await user.type(screen.getByRole("textbox", { name: "Filter documents" }), "contr");
    expect(screen.queryByText("capitolato.pdf")).not.toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: "contratto.pdf" }));
    await user.type(screen.getByRole("textbox", { name: "Model" }), "claude");
    await user.click(await screen.findByRole("button", { name: "Start" }));

    await waitFor(() =>
      expect(generationApi.create).toHaveBeenCalledWith(
        expect.objectContaining({ document_ids: ["d-2"], excluded_document_ids: [] }),
      ),
    );
  });
});
