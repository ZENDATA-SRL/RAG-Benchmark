import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";

import { errorToastText } from "./errors";
import { toast } from "./toast";

export function createQueryClient(): QueryClient {
  return new QueryClient({
    queryCache: new QueryCache({
      onError: (error, query) => {
        if (query.meta?.silent) {
          return;
        }
        toast.error(errorToastText(error));
      },
    }),
    mutationCache: new MutationCache({
      onError: (error, _variables, _context, mutation) => {
        if (mutation.meta?.silent) {
          return;
        }
        toast.error(errorToastText(error));
      },
    }),
    defaultOptions: {
      queries: {
        retry: 1,
        refetchOnWindowFocus: false,
        staleTime: 10_000,
      },
    },
  });
}

export const queryKeys = {
  health: ["health"] as const,
  corpora: ["corpora"] as const,
  corpus: (id: string) => ["corpora", id] as const,
  corpusDocuments: (id: string) => ["corpora", id, "documents"] as const,
  corpusProgress: (id: string) => ["corpora", id, "progress"] as const,
  corpusSnapshots: (id: string) => ["corpora", id, "snapshots"] as const,
  document: (id: string) => ["documents", id] as const,
  documentContent: (id: string) => ["documents", id, "content"] as const,
  components: ["components"] as const,
  configurations: ["configurations"] as const,
  configuration: (id: string) => ["configurations", id] as const,
  coverage: (configurationId: string, corpusId: string) =>
    ["configurations", configurationId, "coverage", corpusId] as const,
  embeddingProfiles: ["embedding-profiles"] as const,
  vectorStoreProfiles: ["vector-store-profiles"] as const,
  retrievalProfiles: ["retrieval-profiles"] as const,
  indexBuilds: ["index-builds"] as const,
  indexBuild: (id: string) => ["index-builds", id] as const,
  materializations: (filters: Record<string, string | undefined>) =>
    ["materializations", filters] as const,
  materialization: (id: string) => ["materializations", id] as const,
  qaSets: ["qa-sets"] as const,
  /** Prefix of every query about one set, whatever configuration it was read under. */
  qaSetScope: (id: string) => ["qa-sets", id] as const,
  qaSet: (id: string, configurationId = "") => ["qa-sets", id, configurationId] as const,
  evidenceCoverage: (id: string, configurationId: string) =>
    ["qa-sets", id, "evidence-coverage", configurationId] as const,
  question: (id: string, configurationId = "") => ["questions", id, configurationId] as const,
  evidence: (questionId: string, configurationId: string) =>
    ["questions", questionId, "evidence", configurationId] as const,
  allChunks: (documentId: string, configurationId: string) =>
    ["chunks", documentId, configurationId, "all"] as const,
  qaSetSnapshots: (id: string) => ["qa-sets", id, "snapshots"] as const,
  experiments: ["experiments"] as const,
  experiment: (id: string) => ["experiments", id] as const,
  coverageCheck: (corpusSnapshotId: string, qaSetSnapshotId: string) =>
    ["experiments", "coverage", corpusSnapshotId, qaSetSnapshotId] as const,
  run: (experimentId: string, runId: string) =>
    ["experiments", experimentId, "runs", runId] as const,
  runResults: (experimentId: string, runId: string, tag: string) =>
    ["experiments", experimentId, "runs", runId, "results", tag] as const,
  runQuestions: (experimentId: string, runId: string) =>
    ["experiments", experimentId, "runs", runId, "questions"] as const,
  runQuestion: (experimentId: string, runId: string, questionId: string) =>
    ["experiments", experimentId, "runs", runId, "questions", questionId] as const,
  chunks: (documentId: string, configurationId: string) =>
    ["chunks", documentId, configurationId] as const,
  parse: (documentId: string, profileId: string) => ["parse", documentId, profileId] as const,
  compare: (documentId: string, configurationIds: string[]) =>
    ["chunks", documentId, "compare", ...configurationIds] as const,
};
