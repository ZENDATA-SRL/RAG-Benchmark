import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ComparisonRead, ComparisonVariantRead, MetricResultRead } from "@/api/types";

import { ComparisonPage } from "./ComparisonPage";

vi.mock("@/api/resources", () => ({
  qaSetsApi: {
    list: async () => ({ items: [{ id: "qs", name: "contracts" }], total: 1 }),
    snapshots: async () => ({
      items: [{ id: "snap", label: "frozen", question_count: 50 }],
      total: 1,
    }),
  },
  experimentsApi: { compare: async () => COMPARISON },
}));

afterEach(cleanup);

function metric(key: string, mean: number, n: number): MetricResultRead {
  return {
    key,
    family: "retrieval",
    level: "document",
    direction: "higher_is_better",
    aggregation: "mean",
    description: `What ${key} measures.`,
    mean,
    stddev: 0,
    median: mean,
    p95: mean,
    n_effective: n,
    n_excluded: 50 - n,
    excluded_reasons: {},
  };
}

function variant(
  name: string,
  recall: number,
  n: number,
  corpus = "v1",
  isBaseline = false,
): ComparisonVariantRead {
  return {
    variant_id: name,
    name,
    is_baseline: isBaseline,
    index_build_id: "build",
    retrieval_profile_id: "profile",
    top_k: 5,
    metrics: [metric("recall@5", recall, n)],
    experiment_id: "experiment",
    experiment_name: "exp",
    run_id: "run",
    corpus_snapshot: { id: corpus, label: corpus },
    chunking_configuration_id: "chunking",
    chunking_configuration_name: "pypdf + 300",
    recall_ceiling: null,
  };
}

let COMPARISON: ComparisonRead;

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/experiments/compare?qaSet=qs"]}>
        <ComparisonPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ComparisonPage", () => {
  it("draws each metric with the best variant, the change from the baseline and the sample", async () => {
    COMPARISON = {
      qa_set_snapshot: { id: "snap", label: "frozen", question_count: 50 },
      experiment_type: "retrieval",
      variants: [variant("base", 0.6, 50, "v1", true), variant("better", 0.8, 31)],
      skipped: [{ experiment_id: "e2", experiment_name: "not run", reason: "no finished run" }],
    };
    renderPage();

    const chart = await screen.findByTestId("chart-recall@5");
    expect(chart).toHaveTextContent("higher is better");
    expect(chart).toHaveTextContent("What recall@5 measures.");
    const better = within(screen.getByTestId("bar-better"));
    expect(better.getByTestId("delta")).toHaveTextContent("▲ +0.20");
    expect(better.getByTestId("smaller-sample")).toHaveTextContent("⚠ n=31/50");
    expect(within(screen.getByTestId("bar-base")).queryByTestId("delta")).not.toBeInTheDocument();
    expect(screen.getByTestId("summary-better")).toHaveTextContent("1 of 1 metrics");
    expect(screen.getByTestId("skipped-notice")).toHaveTextContent("not run");
    expect(screen.queryByTestId("corpus-notice")).not.toBeInTheDocument();
    // A retrieval comparison has no answer section.
    expect(screen.queryByTestId("section-Answers")).not.toBeInTheDocument();
  });

  it("warns when the variants searched different corpus snapshots", async () => {
    COMPARISON = {
      qa_set_snapshot: { id: "snap", label: "frozen", question_count: 50 },
      experiment_type: "retrieval",
      variants: [variant("a", 0.6, 50, "v1", true), variant("b", 0.8, 50, "v2")],
      skipped: [],
    };
    renderPage();

    expect(await screen.findByTestId("corpus-notice")).toHaveTextContent("v1, v2");
  });
});
