import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { QuestionEditor } from "./QuestionEditor";

const createQuestion = vi.fn<(...args: unknown[]) => Promise<object>>(() => Promise.resolve({}));

vi.mock("@/api/resources", () => ({
  corporaApi: {
    documents: () =>
      Promise.resolve({
        items: [
          { id: "d1", filename: "Capitolato_A.pdf" },
          { id: "d2", filename: "Allegato_tecnico.pdf" },
          { id: "d3", filename: "Manuale_Utente.pdf" },
        ],
        total: 3,
      }),
  },
  qaSetsApi: { createQuestion: (...args: unknown[]) => createQuestion(...args) },
  questionsApi: {},
}));

afterEach(cleanup);

describe("QuestionEditor", () => {
  it("picks gold documents from the origin corpus of a new question", async () => {
    const user = userEvent.setup();
    render(
      <QueryClientProvider client={new QueryClient()}>
        <QuestionEditor qaSetId="set" originCorpusId="corpus" question={null} onClose={vi.fn()} />
      </QueryClientProvider>,
    );

    await user.click(await screen.findByLabelText("Allegato_tecnico.pdf"));
    expect(screen.getByText("1 of 3 selected")).toBeInTheDocument();

    // The filter hides other documents but keeps the selected one in view.
    await user.type(screen.getByLabelText("Filter documents"), "manuale");
    expect(screen.queryByLabelText("Capitolato_A.pdf")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Allegato_tecnico.pdf")).toBeChecked();
    expect(screen.getByLabelText("Manuale_Utente.pdf")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Question"), "Dove sono le penali?");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(createQuestion).toHaveBeenCalledWith(
      "set",
      expect.objectContaining({ gold_document_ids: ["d2"] }),
    );
  });
});
