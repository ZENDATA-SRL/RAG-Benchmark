import { describe, expect, it } from "vitest";

import type {
  AnswerProfileRead,
  ComponentWithVersionsRead,
  IndexBuildRead,
  RetrievalProfileRead,
} from "@/api/types";

import {
  canCreateExperiment,
  crossVariants,
  profilesWithoutCitations,
  selectableBuilds,
  variedDimensions,
} from "./variants";

function build(id: string, snapshot: string, status: IndexBuildRead["status"]): IndexBuildRead {
  return {
    id,
    name: `build-${id}`,
    corpus_snapshot_id: snapshot,
    status,
  } as IndexBuildRead;
}

const PROFILES = [
  { id: "p1", name: "top5" },
  { id: "p2", name: "top10" },
] as RetrievalProfileRead[];

describe("selectable builds", () => {
  it("keeps only ready builds of the chosen snapshot", () => {
    const builds = [
      build("a", "s1", "ready"),
      build("b", "s1", "running"),
      build("c", "s2", "ready"),
      build("d", "s1", "failed"),
    ];
    expect(selectableBuilds(builds, "s1").map((item) => item.id)).toEqual(["a"]);
  });
});

describe("crossVariants", () => {
  it("crosses builds with profiles and marks one baseline", () => {
    const variants = crossVariants([build("a", "s1", "ready")], PROFILES, "a:p2");
    expect(variants).toHaveLength(2);
    expect(variants.map((item) => item.variant.is_baseline)).toEqual([false, true]);
    expect(variants[0].variant).toEqual({
      index_build_id: "a",
      retrieval_profile_id: "p1",
      is_baseline: false,
    });
    expect(variants[0].label).toBe("build-a · top5");
  });

  it("has no baseline when none is chosen", () => {
    const variants = crossVariants([build("a", "s1", "ready")], PROFILES, null);
    expect(variants.some((item) => item.variant.is_baseline)).toBe(false);
  });
});

const ANSWERS = [
  { id: "a1", name: "concise", component_version_id: "rag" },
  { id: "a2", name: "verbose", component_version_id: "agent" },
] as AnswerProfileRead[];

describe("Q&A variants", () => {
  it("cross the answer profiles as a third dimension", () => {
    const variants = crossVariants([build("a", "s1", "ready")], [PROFILES[0]], "a:p1:a2", ANSWERS);
    expect(variants.map((item) => item.label)).toEqual([
      "build-a · top5 · concise",
      "build-a · top5 · verbose",
    ]);
    expect(variants[1].variant).toEqual({
      index_build_id: "a",
      retrieval_profile_id: "p1",
      answer_profile_id: "a2",
      is_baseline: true,
    });
  });

  it("have none until an answer profile is chosen", () => {
    expect(crossVariants([build("a", "s1", "ready")], PROFILES, null, [])).toEqual([]);
  });

  it("say when more than one dimension varies", () => {
    expect(variedDimensions({ builds: 1, retrievalProfiles: 1, answerProfiles: 2 })).toEqual([
      "answer profile",
    ]);
    expect(variedDimensions({ builds: 2, retrievalProfiles: 1, answerProfiles: 2 })).toEqual([
      "index build",
      "answer profile",
    ]);
  });

  it("list the profiles whose system does not cite", () => {
    const components = [
      {
        id: "c",
        type: "answer_system",
        versions: [
          { id: "rag", capabilities: { supports_citations: true } },
          { id: "agent", capabilities: {} },
        ],
      },
    ] as unknown as ComponentWithVersionsRead[];
    expect(profilesWithoutCitations(ANSWERS, components).map((item) => item.id)).toEqual(["a2"]);
  });
});

describe("canCreateExperiment", () => {
  const base = { name: "x", variantCount: 2, uncoveredCount: 0, excludeUncovered: false };

  it("needs a name, variants and a coverage check", () => {
    expect(canCreateExperiment(base)).toBe(true);
    expect(canCreateExperiment({ ...base, name: " " })).toBe(false);
    expect(canCreateExperiment({ ...base, variantCount: 0 })).toBe(false);
    expect(canCreateExperiment({ ...base, uncoveredCount: null })).toBe(false);
  });

  it("requires the explicit choice when questions are uncovered", () => {
    expect(canCreateExperiment({ ...base, uncoveredCount: 3 })).toBe(false);
    expect(canCreateExperiment({ ...base, uncoveredCount: 3, excludeUncovered: true })).toBe(true);
  });
});
