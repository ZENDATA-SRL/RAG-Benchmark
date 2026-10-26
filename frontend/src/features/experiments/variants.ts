import type { IndexBuildRead, RetrievalProfileRead, VariantCreate } from "@/api/types";

/** Only a finished build of the chosen corpus snapshot can be searched by a variant. */
export function selectableBuilds(
  builds: IndexBuildRead[],
  corpusSnapshotId: string,
): IndexBuildRead[] {
  return builds.filter(
    (build) => build.status === "ready" && build.corpus_snapshot_id === corpusSnapshotId,
  );
}

export function variantName(
  build: Pick<IndexBuildRead, "name">,
  profile: Pick<RetrievalProfileRead, "name">,
): string {
  return `${build.name} · ${profile.name}`;
}

/** Every chosen build crossed with every chosen retrieval profile; one may be the baseline. */
export function crossVariants(
  builds: IndexBuildRead[],
  profiles: RetrievalProfileRead[],
  baselineName: string | null,
): VariantCreate[] {
  const variants: VariantCreate[] = [];
  for (const build of builds) {
    for (const profile of profiles) {
      const name = variantName(build, profile);
      variants.push({
        name,
        index_build_id: build.id,
        retrieval_profile_id: profile.id,
        is_baseline: name === baselineName,
      });
    }
  }
  return variants;
}

/** With uncovered questions the user must have made the explicit choice before creating. */
export function canCreateExperiment(state: {
  name: string;
  variantCount: number;
  uncoveredCount: number | null;
  excludeUncovered: boolean;
}): boolean {
  if (!state.name.trim() || state.variantCount === 0 || state.uncoveredCount === null) {
    return false;
  }
  return state.uncoveredCount === 0 || state.excludeUncovered;
}
