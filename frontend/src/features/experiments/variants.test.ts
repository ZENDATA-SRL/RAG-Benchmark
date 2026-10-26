import { describe, expect, it } from "vitest";

import type { IndexBuildRead, RetrievalProfileRead } from "@/api/types";

import { canCreateExperiment, crossVariants, selectableBuilds } from "./variants";

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
    const variants = crossVariants([build("a", "s1", "ready")], PROFILES, "build-a · top10");
    expect(variants).toHaveLength(2);
    expect(variants.map((item) => item.is_baseline)).toEqual([false, true]);
    expect(variants[0]).toMatchObject({ index_build_id: "a", retrieval_profile_id: "p1" });
  });

  it("has no baseline when none is chosen", () => {
    const variants = crossVariants([build("a", "s1", "ready")], PROFILES, null);
    expect(variants.some((item) => item.is_baseline)).toBe(false);
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
