import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { RunProgressPanel } from "./RunProgressPanel";

afterEach(cleanup);

describe("RunProgressPanel", () => {
  it("shows the counters and offers resume on a finished run with leftovers", () => {
    render(
      <RunProgressPanel
        run={{
          status: "failed",
          progress: { total: 10, succeeded: 6, failed: 2, pending: 2 },
          error: null,
        }}
        onResume={() => undefined}
        onCancel={() => undefined}
      />,
    );
    expect(screen.getByTestId("progress-succeeded")).toHaveTextContent("6");
    expect(screen.getByTestId("progress-failed")).toHaveTextContent("2");
    expect(screen.getByRole("button", { name: "Resume" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
  });

  it("offers cancel while running", () => {
    render(
      <RunProgressPanel
        run={{
          status: "running",
          progress: { total: 10, succeeded: 1, failed: 0, pending: 9 },
          error: null,
        }}
        onResume={() => undefined}
        onCancel={() => undefined}
      />,
    );
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Resume" })).not.toBeInTheDocument();
  });
});
