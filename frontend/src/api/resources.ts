import { api, uploadFiles, type UploadProgressHandler } from "./client";
import type {
  ChunkComparisonRead,
  ChunkingConfigurationComposed,
  ChunkingConfigurationCompose,
  ChunkingConfigurationCoverage,
  ChunkingConfigurationExpanded,
  ComponentWithVersionsRead,
  CorpusCreate,
  CorpusDocumentRemoved,
  CorpusProgress,
  CorpusRead,
  CorpusUpdate,
  DocumentChunksRead,
  DocumentParseRead,
  DocumentRead,
  DocumentWithProvenancesRead,
  MaterializationAccepted,
  MaterializationDetail,
  MaterializationRead,
  Page,
  UploadResponse,
} from "./types";

export const corporaApi = {
  list: () => api.get<Page<CorpusRead>>("/api/v1/corpora", { limit: 200 }),
  get: (id: string) => api.get<CorpusRead>(`/api/v1/corpora/${id}`),
  create: (body: CorpusCreate) => api.post<CorpusRead>("/api/v1/corpora", body),
  update: (id: string, body: CorpusUpdate) => api.patch<CorpusRead>(`/api/v1/corpora/${id}`, body),
  documents: (id: string) =>
    api.get<Page<DocumentRead>>(`/api/v1/corpora/${id}/documents`, { limit: 200 }),
  progress: (id: string) => api.get<CorpusProgress>(`/api/v1/corpora/${id}/progress`),
  removeDocument: (corpusId: string, documentId: string) =>
    api.delete<CorpusDocumentRemoved>(`/api/v1/corpora/${corpusId}/documents/${documentId}`),
};

export const documentsApi = {
  get: (id: string) => api.get<DocumentWithProvenancesRead>(`/api/v1/documents/${id}`),
  upload: (corpusId: string, files: File[], onProgress?: UploadProgressHandler) =>
    uploadFiles(`/api/v1/corpora/${corpusId}/documents/upload`, files, onProgress) as Promise<UploadResponse>,
};

export const componentsApi = {
  list: (type?: string) =>
    api.get<ComponentWithVersionsRead[]>("/api/v1/components", { type, only_available: false }),
};

export const configurationsApi = {
  list: () =>
    api.get<Page<ChunkingConfigurationExpanded>>("/api/v1/chunking-configurations", { limit: 200 }),
  get: (id: string) => api.get<ChunkingConfigurationExpanded>(`/api/v1/chunking-configurations/${id}`),
  compose: (body: ChunkingConfigurationCompose) =>
    api.post<ChunkingConfigurationComposed>("/api/v1/chunking-configurations/compose", body),
  coverage: (configurationId: string, corpusId: string) =>
    api.get<ChunkingConfigurationCoverage>(
      `/api/v1/chunking-configurations/${configurationId}/coverage`,
      { corpus_id: corpusId },
    ),
};

export const materializationsApi = {
  start: (body: {
    chunking_configuration_id: string;
    document_ids?: string[];
    corpus_id?: string;
  }) => api.post<MaterializationAccepted>("/api/v1/materializations", body),
  list: (filters: { corpus_id?: string; chunking_configuration_id?: string }) =>
    api.get<Page<MaterializationRead>>("/api/v1/materializations", { ...filters, limit: 50 }),
  get: (id: string) => api.get<MaterializationDetail>(`/api/v1/materializations/${id}`),
  cancel: (id: string) => api.post<MaterializationRead>(`/api/v1/materializations/${id}/cancel`),
};

export const inspectionApi = {
  chunks: (documentId: string, configurationId: string) =>
    api.get<DocumentChunksRead>(`/api/v1/documents/${documentId}/chunks`, {
      chunking_configuration_id: configurationId,
      limit: 200,
    }),
  parse: (documentId: string, parsingProfileId: string, offset = 0) =>
    api.get<DocumentParseRead>(`/api/v1/documents/${documentId}/parse`, {
      parsing_profile_id: parsingProfileId,
      limit: 20,
      offset,
    }),
  compare: (documentId: string, configurationIds: string[]) =>
    api.get<ChunkComparisonRead>(`/api/v1/documents/${documentId}/chunks/compare`, {
      configurations: configurationIds.join(","),
      limit: 200,
    }),
};
