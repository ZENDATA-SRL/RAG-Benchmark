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

  it("names the answer systems that do not cite", () => {
    const error = new ApiError(422, {
      code: "citations_not_supported",
      message: "x",
      details: { answer_profiles: ["agent@1"] },
    });
    expect(experimentErrorMessage(error)).toContain("agent@1");
  });

  it("gives the reason an answer system cannot run", () => {
    const error = new ApiError(422, {
      code: "answer_system_not_available",
      message: "x",
      details: { reason: "openai: OPENAI_API_KEY is not set" },
    });
    expect(experimentErrorMessage(error)).toContain("OPENAI_API_KEY");
  });

  it("ignores other errors", () => {
    expect(experimentErrorMessage(new Error("boom"))).toBeNull();
  });
});
