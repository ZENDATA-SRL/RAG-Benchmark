import type {
  AnswerProfileRead,
  ComponentWithVersionsRead,
  IndexBuildRead,
  RetrievalProfileRead,
  VariantCreate,
} from "@/api/types";

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
 * A variant as the wizard lists it. The server names the variant after what it searches and
 * who answers; until then it is shown by its index build, retrieval profile and, for Q&A,
 * answer profile.
 */
export interface VariantChoice {
  key: string;
  label: string;
  variant: VariantCreate;
}

/**
 * Every chosen build crossed with every chosen retrieval profile and, in a Q&A experiment,
 * every chosen answer profile; one may be the baseline. `answerProfiles` is null for a
 * retrieval experiment, which has no third dimension.
 */
export function crossVariants(
  builds: IndexBuildRead[],
  profiles: RetrievalProfileRead[],
  baselineKey: string | null,
  answerProfiles: AnswerProfileRead[] | null = null,
): VariantChoice[] {
  const choices: VariantChoice[] = [];
  for (const build of builds) {
    for (const profile of profiles) {
      for (const answer of answerProfiles ?? [null]) {
        const key = answer ? `${build.id}:${profile.id}:${answer.id}` : `${build.id}:${profile.id}`;
        choices.push({
          key,
          label: [build.name, profile.name, answer?.name].filter(Boolean).join(" · "),
          variant: {
            index_build_id: build.id,
            retrieval_profile_id: profile.id,
            ...(answer ? { answer_profile_id: answer.id } : {}),
            is_baseline: key === baselineKey,
          },
        });
      }
    }
  }
  return choices;
}

/**
 * The dimensions the variants differ on. In a Q&A experiment, varying the answer profile
 * together with the index or the retrieval profile mixes their effects: the wizard says so.
 */
export function variedDimensions(counts: {
  builds: number;
  retrievalProfiles: number;
  answerProfiles: number;
}): string[] {
  return [
    counts.builds > 1 ? "index build" : null,
    counts.retrievalProfiles > 1 ? "retrieval profile" : null,
    counts.answerProfiles > 1 ? "answer profile" : null,
  ].filter((item): item is string => item !== null);
}

/**
 * The chosen answer profiles whose system does not declare citations: the `cited` scope
 * needs every one of them to cite, or its set metrics would all be excluded.
 */
export function profilesWithoutCitations(
  answerProfiles: AnswerProfileRead[],
  components: ComponentWithVersionsRead[],
): AnswerProfileRead[] {
  const citing = new Set(
    components
      .flatMap((component) => component.versions ?? [])
      .filter((version) => version.capabilities?.supports_citations === true)
      .map((version) => version.id),
  );
  return answerProfiles.filter((profile) => !citing.has(profile.component_version_id));
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
