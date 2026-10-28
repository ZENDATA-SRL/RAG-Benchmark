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

/**
 * A variant as the wizard lists it. The server names the variant after what it searches;
 * until then it is shown by its index build and retrieval profile.
 */
export interface VariantChoice {
  key: string;
  label: string;
  variant: VariantCreate;
}

/** Every chosen build crossed with every chosen retrieval profile; one may be the baseline. */
export function crossVariants(
  builds: IndexBuildRead[],
  profiles: RetrievalProfileRead[],
  baselineKey: string | null,
): VariantChoice[] {
  const choices: VariantChoice[] = [];
  for (const build of builds) {
    for (const profile of profiles) {
      const key = `${build.id}:${profile.id}`;
      choices.push({
        key,
        label: `${build.name} · ${profile.name}`,
        variant: {
          index_build_id: build.id,
          retrieval_profile_id: profile.id,
          is_baseline: key === baselineKey,
        },
      });
    }
  }
  return choices;
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
