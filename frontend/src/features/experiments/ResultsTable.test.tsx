import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import type { MetricResultRead, RunResultsRead, VariantResultRead } from "@/api/types";

import { ResultsTable } from "./ResultsTable";

afterEach(cleanup);

function metric(key: string, mean: number, overrides: Partial<MetricResultRead> = {}) {
  return {
    key,
    family: "retrieval",
    level: key.startsWith("chunk_") ? "chunk" : "document",
    direction: "higher_is_better",
    aggregation: "mean",
    description: `What ${key} measures.`,
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
  experiment_type: "retrieval",
  status: "succeeded",
  repetitions: 1,
  question_count: 50,
  corpus_snapshot: { id: "cs", label: "v1", document_count: 20 },
  qa_set_snapshot: { id: "qs", label: "frozen", question_count: 50 },
  slice_key: "all",
  slice_value: "all",
  chunk_gold: { evaluated_at: "2026-10-26T10:00:00Z", hash: "abc" },
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
    // A retrieval run has the ranked metrics only.
    expect(screen.queryByTestId("result-sections")).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "set_recall" })).not.toBeInTheDocument();
    const cell = within(screen.getByTestId("result-row-small-a")).getByText("0.64 (38/50)");
    expect(cell).toHaveAttribute("title", "evidence not found: 9\nevidence not reviewed: 3");
  });

  it("explains every column in a tooltip and in a guide below the table", async () => {
    const user = userEvent.setup();
    render(<ResultsTable results={RESULTS} cutoff={5} />);

    expect(screen.getByRole("columnheader", { name: "recall@5" })).toHaveAttribute(
      "title",
      "What recall@5 measures.",
    );
    const guide = screen.getByTestId("metric-guide");
    await user.click(within(guide).getByText("How to read these metrics"));
    expect(guide).toHaveTextContent("What chunk_recall@5 measures.");
    expect(guide).toHaveTextContent("higher is better · mean over questions");
  });

  it("keeps every column when the selected variants come from different groups", async () => {
    const user = userEvent.setup();
    render(<ResultsTable results={RESULTS} cutoff={5} />);

    await user.click(screen.getByLabelText("Select small-a"));
    await user.click(screen.getByLabelText("Select large-a"));
    await user.click(screen.getByRole("button", { name: "Compare selected (2)" }));

    expect(screen.queryByTestId("result-row-small-b")).not.toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "chunk_recall@5" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "recall@5" })).toBeInTheDocument();
  });
});

describe("ResultsTable on a Q&A run", () => {
  const qa: RunResultsRead = {
    ...RESULTS,
    experiment_type: "qa",
    groups: RESULTS.groups.map((group) => ({
      ...group,
      variants: group.variants.map((item) => ({
        ...item,
        metrics: [
          ...item.metrics,
          metric("set_recall", 0.9),
          metric("retrieved_set_size", 7.5, { family: "efficiency", level: null }),
          metric("duplicate_hit_rate", 0.25, { family: "efficiency", level: null }),
          metric("refusal_accuracy", 0.92, { family: "answer", level: null }),
          metric("answer_latency_ms", 1500, {
            family: "efficiency",
            level: null,
            median: 1840.4,
            p95: 4100,
          }),
        ],
      })),
    })),
  };

  it("adds the set and call sections, with the set size next to the set recall", () => {
    render(<ResultsTable results={qa} cutoff={5} />);

    const sections = screen.getByTestId("result-sections");
    expect(sections).toHaveTextContent("Ranked, first call");
    expect(sections).toHaveTextContent("Set");
    expect(sections).toHaveTextContent("Calls");
    const headers = screen.getAllByRole("columnheader").map((cell) => cell.textContent);
    const at = headers.indexOf("set_recall");
    expect(headers.slice(at, at + 3)).toEqual([
      "set_recall",
      "retrieved_set_size",
      "duplicate_hit_rate",
    ]);
    expect(within(screen.getByTestId("result-row-small-a")).getByText("0.25 (38/50)")).toBeTruthy();
  });

  it("adds the answer section, with latency on its median and p95", () => {
    render(<ResultsTable results={qa} cutoff={5} />);

    expect(screen.getByTestId("result-sections")).toHaveTextContent("Answer");
    const row = within(screen.getByTestId("result-row-small-a"));
    expect(row.getByText("0.92 (38/50)")).toBeTruthy();
    expect(row.getByText("1840 (38/50)")).toBeTruthy();
    expect(row.getByText("4100 (38/50)")).toBeTruthy();
  });

  it("keeps the chunk-level set columns across chunking configurations", async () => {
    const user = userEvent.setup();
    render(<ResultsTable results={qa} cutoff={5} />);

    await user.click(screen.getByLabelText("Select small-a"));
    await user.click(screen.getByLabelText("Select large-a"));
    await user.click(screen.getByRole("button", { name: "Compare selected (2)" }));

    expect(screen.getByRole("columnheader", { name: "set_recall" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "chunk_set_recall" })).toBeInTheDocument();
  });
});
