import { describe, expect, it } from "vitest";

import { describeOutcome, excerpt } from "./outcome";

describe("describeOutcome", () => {
  it("describes rank, miss, exclusion and failure", () => {
    expect(describeOutcome({ status: "succeeded", first_relevant_rank: 2 })).toBe("rank 2");
    expect(describeOutcome({ status: "succeeded", first_relevant_rank: null })).toBe("not found");
    expect(describeOutcome({ status: "skipped", excluded_reason: "gold_outside_snapshot" })).toBe(
      "excluded: gold_outside_snapshot",
    );
    expect(describeOutcome({ status: "failed" })).toBe("failed");
    expect(describeOutcome(undefined)).toBe("—");
  });
});

describe("excerpt", () => {
  it("shortens long text only", () => {
    expect(excerpt("short")).toBe("short");
    expect(excerpt("x".repeat(200))).toHaveLength(161);
    expect(excerpt(null)).toBe("");
  });
});
