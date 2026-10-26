import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { DraftChunk } from "./evidence";
import { EvidencePanel } from "./EvidencePanel";

afterEach(cleanup);

const CHUNK: DraftChunk = {
  chunk_id: "c1",
  relevance: "sufficient",
  document_id: "d1",
  filename: "Capitolato_A.pdf",
  ordinal: 12,
  text: "La penale per ritardo è dell'1 per mille al giorno.",
};

function renderPanel(overrides: Partial<Parameters<typeof EvidencePanel>[0]> = {}) {
  const props = {
    status: "not_reviewed" as const,
    draft: [] as DraftChunk[],
    dirty: false,
    annotator: "",
    onAnnotatorChange: vi.fn(),
    onRelevance: vi.fn(),
    onOpen: vi.fn(),
    onSave: vi.fn(),
    saving: false,
    ...overrides,
  };
  render(<EvidencePanel {...props} />);
  return props;
}

describe("EvidencePanel", () => {
  it("only lets a draft be saved while nothing is picked and no name is given", () => {
    renderPanel();

    expect(screen.getByRole("button", { name: "Confirm" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Not found" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save draft" })).toBeEnabled();
    expect(screen.getByTestId("evidence-hint")).toHaveTextContent(/at least one chunk/);
  });

  it("confirms picked chunks once the annotator is named", async () => {
    const user = userEvent.setup();
    const props = renderPanel({ draft: [CHUNK], dirty: true, annotator: "anna" });

    expect(screen.getByText("unsaved")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Not found" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Confirm" }));

    expect(props.onSave).toHaveBeenCalledWith("confirmed");
  });

  it("changes the grade of a chunk and removes it", async () => {
    const user = userEvent.setup();
    const props = renderPanel({ draft: [CHUNK] });

    await user.selectOptions(screen.getByLabelText("Relevance of chunk 12"), "supporting");
    expect(props.onRelevance).toHaveBeenCalledWith(CHUNK, "supporting");

    await user.click(screen.getByRole("button", { name: "Remove chunk 12" }));
    expect(props.onRelevance).toHaveBeenLastCalledWith(CHUNK, null);

    await user.click(screen.getByRole("button", { name: "Capitolato_A.pdf #12" }));
    expect(props.onOpen).toHaveBeenCalledWith(CHUNK);
  });

  it("shows who took the decision", () => {
    renderPanel({ status: "not_found", confirmedBy: "bruno", confirmedAt: null });

    expect(screen.getByText("not found")).toBeInTheDocument();
    expect(screen.getByText(/Decided by bruno/)).toBeInTheDocument();
  });
});
