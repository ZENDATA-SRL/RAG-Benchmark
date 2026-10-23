import type {
  RetrievalProfileRead,
  RetrievalStrategy,
  RetrievedHitRead,
  RetrieveResponse,
} from "@/api/types";

/** Every value of the API's strategy enum; only `dense` is executable today. */
export const RETRIEVAL_STRATEGIES: RetrievalStrategy[] = [
  "dense",
  "sparse",
  "hybrid",
  "multi_vector",
];

/** Form schema of the retrieval profile fields the engine applies today. */
export const RETRIEVAL_PROFILE_SCHEMA = {
  type: "object",
  required: ["strategy", "top_k"],
  properties: {
    strategy: {
      type: "string",
      title: "Search strategy",
      description: "Only dense search is available today; the API refuses the others.",
      enum: RETRIEVAL_STRATEGIES,
      default: "dense",
    },
    top_k: {
      type: "integer",
      title: "Top-k",
      description: "How many chunks a query returns.",
      minimum: 1,
      maximum: 200,
      default: 5,
    },
    score_threshold: {
      type: "number",
      title: "Score threshold (optional)",
      description:
        "Drop hits scoring below this value. Scores are higher-is-better on every store.",
    },
  },
} as const;

/** One-line description of a retrieval profile, for the selector. */
export function describeProfile(profile: RetrievalProfileRead): string {
  const parts = [profile.strategy, `top-${profile.top_k}`];
  if (profile.score_threshold !== null && profile.score_threshold !== undefined) {
    parts.push(`≥ ${profile.score_threshold}`);
  }
  return parts.join(" · ");
}

/** Chunk viewer link for a hit, or null when its chunk no longer exists in the database. */
export function hitLink(response: RetrieveResponse, hit: RetrievedHitRead): string | null {
  if (!hit.chunk_id || !hit.document_id || !response.corpus_id) return null;
  const params = new URLSearchParams({
    configuration: response.chunking_configuration_id,
    chunk: hit.chunk_id,
  });
  return `/corpora/${response.corpus_id}/documents/${hit.document_id}/chunks?${params}`;
}

/** Where the time of a query went, e.g. "84 ms (embed 60 · search 20 · read 4)". */
export function describeTimings(timings: RetrieveResponse["timings"]): string {
  const round = (value: number) => Math.round(value);
  return `${round(timings.total_ms)} ms (embed ${round(timings.embed_ms)} · search ${round(
    timings.search_ms,
  )} · read ${round(timings.enrich_ms)})`;
}
