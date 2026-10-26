import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import type { MetricResultRead, RunResultsRead, VariantResultRead } from "@/api/types";

import { ResultsTable } from "./ResultsTable";

afterEach(cleanup);

function metric(key: string, mean: number, overrides: Partial<MetricResultRead> = {}) {
  return {
    key,
    level: key.startsWith("chunk_") ? "chunk" : "document",
    direction: "higher_is_better",
    mean,
    stddev: 0,
    median: mean,
    p95: mean,
    n_effective: 38,
    n_excluded: 12,
    excluded_reasons: { evidence_not_found: 9, evidence_not_reviewed: 3 },
    ...overrides,
  } satisfies MetricResultRead;
}

function variant(name: string): VariantResultRead {
  return {
    variant_id: name,
    name,
    is_baseline: name === "small-a",
    index_build_id: `build-${name}`,
    retrieval_profile_id: "profile",
    top_k: 5,
    metrics: [metric("recall@5", 0.8), metric("chunk_recall@5", 0.64)],
  };
}

const RESULTS: RunResultsRead = {
  run_id: "run",
  experiment_id: "experiment",
  status: "succeeded",
  repetitions: 1,
  question_count: 50,
  corpus_snapshot: { id: "cs", label: "v1", document_count: 20 },
  qa_set_snapshot: { id: "qs", label: "frozen", question_count: 50 },
  slice_key: "all",
  slice_value: "all",
  chunk_gold: { evaluated_at: "2026-10-26T10:00:00Z", hash: "abc" },
  cross_group_metrics: {
    keys: ["recall@5"],
    reason: "Chunk-level metrics only compare within one chunking configuration.",
  },
  groups: [
    {
      chunking_configuration_id: "small",
      chunking_configuration_name: "pypdf + 300",
      parsing: "pypdf",
      chunking: "chunk300",
      evidence_coverage: {
        answerable: 50,
        confirmed: 38,
        not_found: 9,
        to_review: 0,
        not_reviewed: 3,
      },
      recall_ceiling: 0.81,
      variants: [variant("small-a"), variant("small-b")],
    },
    {
      chunking_configuration_id: "large",
      chunking_configuration_name: "pypdf + 1000",
      parsing: "pypdf",
      chunking: "chunk1000",
      evidence_coverage: null,
      recall_ceiling: null,
      variants: [variant("large-a")],
    },
  ],
};

describe("ResultsTable", () => {
  it("groups the variants by chunking configuration, with evidence and ceiling", () => {
    render(<ResultsTable results={RESULTS} cutoff={5} />);

    const small = screen.getByTestId("result-group-small");
    expect(small).toHaveTextContent("pypdf + 300");
    expect(small).toHaveTextContent("38 confirmed · 9 not found · 0 to review · 3 not reviewed");
    expect(small).toHaveTextContent("recall ceiling 0.81");
    expect(screen.getByTestId("result-group-large")).toHaveTextContent("re-evaluate");
    expect(screen.getByRole("columnheader", { name: "chunk_recall@5" })).toBeInTheDocument();
    const cell = within(screen.getByTestId("result-row-small-a")).getByText("0.64 (38/50)");
    expect(cell).toHaveAttribute("title", "evidence not found: 9\nevidence not reviewed: 3");
  });

  it("keeps chunk columns within a group and drops them across groups, saying why", async () => {
    const user = userEvent.setup();
    render(<ResultsTable results={RESULTS} cutoff={5} />);

    await user.click(screen.getByLabelText("Select small-a"));
    await user.click(screen.getByLabelText("Select small-b"));
    await user.click(screen.getByRole("button", { name: "Compare selected (2)" }));
    expect(screen.queryByTestId("result-row-large-a")).not.toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "chunk_recall@5" })).toBeInTheDocument();
    expect(screen.queryByTestId("cross-group-reason")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Show all" }));
    await user.click(screen.getByLabelText("Select small-b"));
    await user.click(screen.getByLabelText("Select large-a"));
    await user.click(screen.getByRole("button", { name: "Compare selected (2)" }));
    expect(screen.queryByRole("columnheader", { name: "chunk_recall@5" })).not.toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "recall@5" })).toBeInTheDocument();
    expect(screen.getByTestId("cross-group-reason")).toHaveTextContent(
      "only compare within one chunking configuration",
    );
  });
});
