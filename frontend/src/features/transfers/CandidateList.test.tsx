import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CandidateRead } from "@/api/types";

import { CandidateList } from "./CandidateList";

afterEach(cleanup);

const CANDIDATES: CandidateRead[] = [
  {
    chunk_id: "c1",
    document_id: "d1",
    filename: "Capitolato.pdf",
    ordinal: 12,
    page: 4,
    text: "La penale per ritardo è dell'1 per mille al giorno.",
    rank: 1,
    combined_score: 0.91,
    semantic_score: 0.8,
    lexical_score: 0.97,
    positional_score: 1,
    confidence: "high",
    preselected: true,
    suggested_relevance: "sufficient",
  },
  {
    chunk_id: "c2",
    document_id: "d1",
    filename: "Capitolato.pdf",
    ordinal: 13,
    page: 4,
    text: "Il pagamento avviene a sessanta giorni.",
    rank: 2,
    combined_score: 0.3,
    semantic_score: 0.4,
    lexical_score: 0.1,
    positional_score: null,
    confidence: "low",
    preselected: false,
    suggested_relevance: null,
  },
];

describe("CandidateList", () => {
  it("shows each candidate with its band, scores and grade, and grades it", async () => {
    const user = userEvent.setup();
    const onMark = vi.fn();
    const onOpen = vi.fn();
    render(
      <CandidateList
        candidates={CANDIDATES}
        grades={new Map([["c1", "sufficient"]])}
        selectedIndex={0}
        onSelect={vi.fn()}
        onMark={onMark}
        onOpen={onOpen}
      />,
    );

    const [first, second] = screen.getAllByTestId("candidate");
    expect(first).toHaveTextContent("pre-selected");
    expect(first).toHaveTextContent("0.91 · sem 0.80 · lex 0.97 · pos 1.00");
    expect(
      within(first).getByRole("button", { name: "Mark chunk 12 as sufficient" }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(second).toHaveTextContent("pos —");

    await user.click(within(second).getByRole("button", { name: "Mark chunk 13 as supporting" }));
    expect(onMark).toHaveBeenCalledWith(CANDIDATES[1], "supporting");
    await user.click(within(second).getByRole("button", { name: "Capitolato.pdf #13 · p. 4" }));
    expect(onOpen).toHaveBeenCalledWith(CANDIDATES[1]);
  });

  it("says what to do when there is no candidate", () => {
    render(
      <CandidateList
        candidates={[]}
        grades={new Map()}
        selectedIndex={0}
        onSelect={vi.fn()}
        onMark={vi.fn()}
        onOpen={vi.fn()}
      />,
    );

    expect(screen.getByText(/Search the chunks/)).toBeInTheDocument();
  });
});
