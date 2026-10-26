import { api, apiFetch, apiUrl, uploadFiles, type UploadProgressHandler } from "./client";
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
  CorpusSnapshotCreate,
  CorpusSnapshotCreated,
  CorpusSnapshotRead,
  CorpusUpdate,
  DocumentChunksRead,
  DocumentParseRead,
  DocumentRead,
  DocumentWithProvenancesRead,
  EmbeddingProfileCreate,
  EmbeddingProfileCreated,
  EmbeddingProfileRead,
  IndexBuildAccepted,
  IndexBuildCreate,
  IndexBuildCreated,
  IndexBuildDetail,
  IndexBuildRead,
  MaterializationAccepted,
  MaterializationDetail,
  MaterializationRead,
  Page,
  QASetCreate,
  QASetDetail,
  QASetRead,
  QASetSnapshotCreated,
  QASetSnapshotRead,
  QuestionCreate,
  QuestionRead,
  QuestionUpdate,
  EvidenceCoverageRead,
  EvidenceRead,
  EvidenceWrite,
  ImportSummaryRead,
  ExperimentCreate,
  ExperimentDetail,
  ExperimentRead,
  CoverageRead,
  RunAccepted,
  RunRead,
  RunDetail,
  RunResultsRead,
  RunQuestionRead,
  QuestionDrilldownRead,
  RetrievalProfileCreate,
  RetrievalProfileCreated,
  RetrievalProfileRead,
  RetrieveRequest,
  RetrieveResponse,
  UploadResponse,
  VectorStoreProfileCreate,
  VectorStoreProfileCreated,
  VectorStoreProfileRead,
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

export const snapshotsApi = {
  list: (corpusId: string) =>
    api.get<Page<CorpusSnapshotRead>>(`/api/v1/corpora/${corpusId}/snapshots`, { limit: 200 }),
  create: (corpusId: string, body: CorpusSnapshotCreate) =>
    api.post<CorpusSnapshotCreated>(`/api/v1/corpora/${corpusId}/snapshots`, body),
};

export const documentsApi = {
  get: (id: string) => api.get<DocumentWithProvenancesRead>(`/api/v1/documents/${id}`),
  upload: (corpusId: string, files: File[], onProgress?: UploadProgressHandler) =>
    uploadFiles(
      `/api/v1/corpora/${corpusId}/documents/upload`,
      files,
      onProgress,
    ) as Promise<UploadResponse>,
};

export const componentsApi = {
  list: (type?: string) =>
    api.get<ComponentWithVersionsRead[]>("/api/v1/components", { type, only_available: false }),
};

export const configurationsApi = {
  list: () =>
    api.get<Page<ChunkingConfigurationExpanded>>("/api/v1/chunking-configurations", { limit: 200 }),
  get: (id: string) =>
    api.get<ChunkingConfigurationExpanded>(`/api/v1/chunking-configurations/${id}`),
  compose: (body: ChunkingConfigurationCompose) =>
    api.post<ChunkingConfigurationComposed>("/api/v1/chunking-configurations/compose", body),
  coverage: (configurationId: string, corpusId: string) =>
    api.get<ChunkingConfigurationCoverage>(
      `/api/v1/chunking-configurations/${configurationId}/coverage`,
      { corpus_id: corpusId },
    ),
};

export const embeddingProfilesApi = {
  list: () => api.get<Page<EmbeddingProfileRead>>("/api/v1/embedding-profiles", { limit: 200 }),
  create: (body: EmbeddingProfileCreate) =>
    api.post<EmbeddingProfileCreated>("/api/v1/embedding-profiles", body),
};

export const vectorStoreProfilesApi = {
  list: () =>
    api.get<Page<VectorStoreProfileRead>>("/api/v1/vector-store-profiles", { limit: 200 }),
  create: (body: VectorStoreProfileCreate) =>
    api.post<VectorStoreProfileCreated>("/api/v1/vector-store-profiles", body),
};

export const retrievalProfilesApi = {
  list: () => api.get<Page<RetrievalProfileRead>>("/api/v1/retrieval-profiles", { limit: 200 }),
  create: (body: RetrievalProfileCreate) =>
    api.post<RetrievalProfileCreated>("/api/v1/retrieval-profiles", body),
};

export const retrievalApi = {
  retrieve: (body: RetrieveRequest) => api.post<RetrieveResponse>("/api/v1/retrieve", body),
};

export const indexBuildsApi = {
  list: (corpusSnapshotId?: string) =>
    api.get<Page<IndexBuildRead>>("/api/v1/index-builds", {
      corpus_snapshot_id: corpusSnapshotId,
      limit: 200,
    }),
  get: (id: string) => api.get<IndexBuildDetail>(`/api/v1/index-builds/${id}`),
  create: (body: IndexBuildCreate) => api.post<IndexBuildCreated>("/api/v1/index-builds", body),
  start: (id: string) => api.post<IndexBuildAccepted>(`/api/v1/index-builds/${id}/start`),
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
  chunks: (documentId: string, configurationId: string, offset = 0) =>
    api.get<DocumentChunksRead>(`/api/v1/documents/${documentId}/chunks`, {
      chunking_configuration_id: configurationId,
      limit: 200,
      offset,
    }),
  /** Every chunk of a document, page after page: annotation must see the whole document. */
  allChunks: async (documentId: string, configurationId: string) => {
    const first = await inspectionApi.chunks(documentId, configurationId);
    const items = [...(first.items ?? [])];
    while (items.length < first.total) {
      const next = await inspectionApi.chunks(documentId, configurationId, items.length);
      if (!next.items?.length) break;
      items.push(...next.items);
    }
    return { ...first, items };
  },
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

export const qaSetsApi = {
  list: () => api.get<Page<QASetRead>>("/api/v1/qa-sets", { limit: 200 }),
  get: (id: string, configurationId?: string) =>
    api.get<QASetDetail>(`/api/v1/qa-sets/${id}`, {
      limit: 200,
      chunking_configuration_id: configurationId,
    }),
  createQuestion: (id: string, body: QuestionCreate) =>
    api.post<QuestionRead>(`/api/v1/qa-sets/${id}/questions`, body),
  evidenceCoverage: (id: string, configurationId: string) =>
    api.get<EvidenceCoverageRead>(`/api/v1/qa-sets/${id}/evidence-coverage`, {
      chunking_configuration_id: configurationId,
    }),
  exportUrl: (id: string, format: "csv" | "jsonl", snapshotId?: string) =>
    apiUrl(
      `/api/v1/qa-sets/${id}/export?format=${format}` +
        (snapshotId ? `&snapshot_id=${snapshotId}` : ""),
    ),
  create: (body: QASetCreate) => api.post<QASetRead>("/api/v1/qa-sets", body),
  importFile: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return apiFetch<ImportSummaryRead>(`/api/v1/qa-sets/${id}/import`, {
      method: "POST",
      body: form,
    });
  },
  freeze: (id: string, label?: string) =>
    api.post<QASetSnapshotCreated>(`/api/v1/qa-sets/${id}/snapshots`, {
      label: label || undefined,
    }),
  snapshots: (id: string) =>
    api.get<Page<QASetSnapshotRead>>(`/api/v1/qa-sets/${id}/snapshots`, { limit: 200 }),
};

export const questionsApi = {
  get: (id: string, configurationId?: string) =>
    api.get<QuestionRead>(`/api/v1/questions/${id}`, {
      chunking_configuration_id: configurationId,
    }),
  update: (id: string, body: QuestionUpdate) =>
    api.patch<QuestionRead>(`/api/v1/questions/${id}`, body),
  remove: (id: string) => api.delete<null>(`/api/v1/questions/${id}`),
  replace: (id: string, body: QuestionCreate) =>
    api.post<QuestionRead>(`/api/v1/questions/${id}/replace`, body),
  setGoldDocuments: (id: string, documentIds: string[]) =>
    api.put<QuestionRead>(`/api/v1/questions/${id}/gold-documents`, {
      document_ids: documentIds,
    }),
  evidence: (id: string, configurationId: string) =>
    api.get<EvidenceRead>(`/api/v1/questions/${id}/evidence`, {
      chunking_configuration_id: configurationId,
    }),
  saveEvidence: (id: string, body: EvidenceWrite) =>
    api.put<EvidenceRead>(`/api/v1/questions/${id}/evidence`, body),
};

export const experimentsApi = {
  list: () => api.get<Page<ExperimentRead>>("/api/v1/experiments", { limit: 200 }),
  get: (id: string) => api.get<ExperimentDetail>(`/api/v1/experiments/${id}`),
  create: (body: ExperimentCreate) => api.post<ExperimentDetail>("/api/v1/experiments", body),
  coverage: (corpusSnapshotId: string, qaSetSnapshotId: string) =>
    api.get<CoverageRead>("/api/v1/experiments/coverage", {
      corpus_snapshot_id: corpusSnapshotId,
      qa_set_snapshot_id: qaSetSnapshotId,
    }),
  startRun: (id: string) => api.post<RunAccepted>(`/api/v1/experiments/${id}/runs`, {}),
  run: (id: string, runId: string) => api.get<RunDetail>(`/api/v1/experiments/${id}/runs/${runId}`),
  cancelRun: (id: string, runId: string) =>
    api.post<RunRead>(`/api/v1/experiments/${id}/runs/${runId}/cancel`),
  resumeRun: (id: string, runId: string) =>
    api.post<RunAccepted>(`/api/v1/experiments/${id}/runs/${runId}/resume`, {}),
  results: (id: string, runId: string, tag?: string) =>
    api.get<RunResultsRead>(`/api/v1/experiments/${id}/runs/${runId}/results`, { tag }),
  resultsCsvUrl: (id: string, runId: string) =>
    apiUrl(`/api/v1/experiments/${id}/runs/${runId}/results.csv`),
  questions: (id: string, runId: string) =>
    api.get<Page<RunQuestionRead>>(`/api/v1/experiments/${id}/runs/${runId}/questions`, {
      limit: 200,
    }),
  question: (id: string, runId: string, questionId: string) =>
    api.get<QuestionDrilldownRead>(
      `/api/v1/experiments/${id}/runs/${runId}/questions/${questionId}`,
    ),
};
