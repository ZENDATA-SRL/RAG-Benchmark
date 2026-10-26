import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/errors";

import { experimentErrorMessage } from "./errors";

describe("experimentErrorMessage", () => {
  it("lists the variants outside the snapshot", () => {
    const error = new ApiError(422, {
      code: "variants_outside_snapshot",
      message: "x",
      details: { variants: [{ name: "v1" }, { name: "v2" }] },
    });
    expect(experimentErrorMessage(error)).toContain("v1, v2");
  });

  it("explains the coverage choice", () => {
    const error = new ApiError(422, {
      code: "gold_coverage_choice_required",
      message: "x",
      details: {},
    });
    expect(experimentErrorMessage(error)).toContain("exclude");
  });

  it("ignores other errors", () => {
    expect(experimentErrorMessage(new Error("boom"))).toBeNull();
  });
});
