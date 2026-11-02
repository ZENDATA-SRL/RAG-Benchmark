import { describe, expect, it } from "vitest";

import {
  annotationUrl,
  describeChunkOutcome,
  describeOccurrences,
  describeOutcome,
  describeUsage,
  excerpt,
  refusalRight,
} from "./outcome";

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

describe("describeOccurrences", () => {
  it("says nothing for a chunk retrieved once and lists every call of a repeated one", () => {
    expect(describeOccurrences([{ call_index: 1, rank: 1 }])).toBe("");
    expect(
      describeOccurrences([
        { call_index: 1, rank: 1 },
        { call_index: 2, rank: 3 },
      ]),
    ).toBe("×2 · call 1 rank 1, call 2 rank 3");
  });
});

describe("describeUsage", () => {
  it("names the model, the tokens and where the time went", () => {
    expect(
      describeUsage({
        usage: { model: "gpt-test", input_tokens: 1834, output_tokens: 112 },
        timings: { total_ms: 1760.9, model_ms: 1532 },
      }),
    ).toBe("gpt-test · 1834 → 112 tokens · 1.8 s (model 1.5 s)");
  });

  it("is empty for an execution that did not answer", () => {
    expect(describeUsage({ usage: null, timings: { total_ms: 12 } })).toBe("");
  });
});

describe("refusalRight", () => {
  it("is right to refuse exactly the unanswerable questions", () => {
    expect(refusalRight(true, false)).toBe(true);
    expect(refusalRight(false, true)).toBe(true);
    expect(refusalRight(true, true)).toBe(false);
    expect(refusalRight(false, false)).toBe(false);
    expect(refusalRight(null, true)).toBeNull();
  });
});
