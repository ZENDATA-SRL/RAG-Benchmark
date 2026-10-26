import { describe, expect, it } from "vitest";

import { annotationUrl, describeChunkOutcome, describeOutcome, excerpt } from "./outcome";

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

describe("describeChunkOutcome", () => {
  it("describes the evidence chunk rank, or why the question does not count", () => {
    expect(describeChunkOutcome({ status: "succeeded", chunk_first_relevant_rank: 3 })).toBe(
      "rank 3",
    );
    expect(describeChunkOutcome({ status: "succeeded", chunk_first_relevant_rank: null })).toBe(
      "not found",
    );
    expect(
      describeChunkOutcome({ status: "succeeded", chunk_excluded_reason: "evidence_not_reviewed" }),
    ).toBe("evidence not reviewed");
    expect(describeChunkOutcome({ status: "failed" })).toBe("—");
  });
});

describe("excerpt", () => {
  it("shortens long text only", () => {
    expect(excerpt("short")).toBe("short");
    expect(excerpt("x".repeat(200))).toHaveLength(161);
    expect(excerpt(null)).toBe("");
  });
});

describe("annotationUrl", () => {
  it("opens the annotation page under a configuration, on a document if given", () => {
    expect(annotationUrl("set", "q", "cfg")).toBe(
      "/qa-sets/set/questions/q/annotate?configuration=cfg",
    );
    expect(annotationUrl("set", "q", "cfg", "doc")).toBe(
      "/qa-sets/set/questions/q/annotate?configuration=cfg&document=doc",
    );
  });
});
