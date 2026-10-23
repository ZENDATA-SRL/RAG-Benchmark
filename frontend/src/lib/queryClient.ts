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
  chunks: (documentId: string, configurationId: string) =>
    ["chunks", documentId, configurationId] as const,
  parse: (documentId: string, profileId: string) => ["parse", documentId, profileId] as const,
  compare: (documentId: string, configurationIds: string[]) =>
    ["chunks", documentId, "compare", ...configurationIds] as const,
};
