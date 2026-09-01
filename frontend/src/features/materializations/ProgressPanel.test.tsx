import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { MaterializationDetail } from "@/api/types";

import { ProgressPanelView } from "./ProgressPanel";

const RUN: MaterializationDetail = {
  id: "run-1",
  chunking_configuration_id: "cfg-1",
  corpus_id: "corpus-1",
  workflow_id: "wf-1",
  status: "ready",
  document_count: 3,
  progress: { ready: 0, cached: 3, failed: 0, pending: 0 },
  error: null,
  started_at: "2026-01-01T00:00:00Z",
  finished_at: "2026-01-01T00:00:02Z",
  created_at: "2026-01-01T00:00:00Z",
  failures: [],
};

describe("ProgressPanel", () => {
  it("shows cached separately from ready", () => {
    render(<ProgressPanelView run={RUN} filenames={new Map()} />);

    expect(screen.getByTestId("progress-ready")).toHaveTextContent("0");
    expect(screen.getByTestId("progress-cached")).toHaveTextContent("3");
    expect(screen.getByText("reused, not recomputed")).toBeInTheDocument();
    expect(screen.getByText("newly computed")).toBeInTheDocument();
  });

  it("lists failed documents with their reason", () => {
    render(
      <ProgressPanelView
        run={{
          ...RUN,
          status: "ready",
          progress: { ready: 1, cached: 0, failed: 1, pending: 0 },
          failures: [{ document_id: "doc-1", error: "encrypted_pdf" }],
        }}
        filenames={new Map([["doc-1", "secret.pdf"]])}
      />,
    );

    expect(screen.getByTestId("progress-failures")).toHaveTextContent("secret.pdf: encrypted_pdf");
  });
});
