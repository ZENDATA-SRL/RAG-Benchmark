import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CreateQaSetDialog } from "./QaSetsPage";

vi.mock("@/api/resources", () => ({
  corporaApi: {
    list: () =>
      Promise.resolve({
        items: [
          { id: "c1", name: "ZENDATA-BENCH" },
          { id: "c2", name: "RAG-SAMPLE-DATA" },
        ],
        total: 2,
      }),
  },
  qaSetsApi: { create: vi.fn() },
}));

afterEach(cleanup);

function renderDialog() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <CreateQaSetDialog onClose={() => undefined} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return {
    name: screen.getByRole("textbox", { name: "Name" }),
    corpus: screen.getByRole("combobox", { name: "Origin corpus (optional)" }),
  };
}

describe("CreateQaSetDialog", () => {
  it("names the set after the chosen corpus until the user types a name", async () => {
    const user = userEvent.setup();
    const { name, corpus } = renderDialog();
    await screen.findByRole("option", { name: "ZENDATA-BENCH" });

    await user.selectOptions(corpus, "c1");
    expect(name).toHaveValue("ZENDATA-BENCH");

    await user.selectOptions(corpus, "c2");
    expect(name).toHaveValue("RAG-SAMPLE-DATA");
  });

  it("keeps a name the user typed", async () => {
    const user = userEvent.setup();
    const { name, corpus } = renderDialog();
    await screen.findByRole("option", { name: "ZENDATA-BENCH" });

    await user.type(name, "My questions");
    await user.selectOptions(corpus, "c1");
    expect(name).toHaveValue("My questions");
  });
});
