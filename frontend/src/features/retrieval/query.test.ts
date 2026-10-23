import { describe, expect, it } from "vitest";

import type { RetrievalProfileRead, RetrieveResponse } from "@/api/types";

import { describeProfile, describeTimings, hitLink } from "./query";

const response: RetrieveResponse = {
  index_build_id: "build",
  retrieval_profile_id: "profile",
  corpus_id: "corpus",
  chunking_configuration_id: "config",
  hits: [],
  timings: { embed_ms: 60.4, search_ms: 20.2, enrich_ms: 3.6, total_ms: 84.2 },
};

const hit = {
  rank: 1,
  score: 0.9,
  stage: "final",
  chunk_id: "chunk",
  document_id: "doc",
  filename: "a.pdf",
  ordinal: 0,
  page: 2,
  text: "text",
};

describe("hitLink", () => {
  it("opens the chunk under the build's configuration", () => {
    expect(hitLink(response, hit)).toBe(
      "/corpora/corpus/documents/doc/chunks?configuration=config&chunk=chunk",
    );
  });

  it("has nowhere to go for a chunk that no longer exists", () => {
    expect(hitLink(response, { ...hit, chunk_id: null })).toBeNull();
  });
});

describe("describeProfile", () => {
  it("lists only what is set", () => {
    const profile: RetrievalProfileRead = {
      id: "p",
      name: "p",
      top_k: 5,
      strategy: "dense",
      score_threshold: 0.3,
      config_hash: "h",
      created_at: "2026-01-01T00:00:00Z",
    };
    expect(describeProfile(profile)).toBe("dense · top-5 · ≥ 0.3");
  });
});

describe("describeTimings", () => {
  it("rounds every step", () => {
    expect(describeTimings(response.timings)).toBe("84 ms (embed 60 · search 20 · read 4)");
  });
});
