import type { components } from "./schema";

export type CorpusRead = components["schemas"]["CorpusRead"];
export type CorpusCreate = components["schemas"]["CorpusCreate"];
export type CorpusUpdate = components["schemas"]["CorpusUpdate"];
export type CorpusProgress = components["schemas"]["CorpusProgress"];
export type CorpusDocumentRemoved = components["schemas"]["CorpusDocumentRemoved"];
export type CorpusSnapshotRead = components["schemas"]["CorpusSnapshotRead"];
export type CorpusSnapshotCreate = components["schemas"]["CorpusSnapshotCreate"];
export type CorpusSnapshotCreated = components["schemas"]["CorpusSnapshotCreated"];

export type DocumentRead = components["schemas"]["DocumentRead"];
export type DocumentWithProvenancesRead = components["schemas"]["DocumentWithProvenancesRead"];
export type DocumentProvenanceRead = components["schemas"]["DocumentProvenanceRead"];
export type UploadResponse = components["schemas"]["UploadResponse"];
export type UploadFileResult = components["schemas"]["UploadFileResult"];

export type ComponentWithVersionsRead = components["schemas"]["ComponentWithVersionsRead"];
export type ComponentRead = components["schemas"]["ComponentRead"];
export type ComponentVersionRead = components["schemas"]["ComponentVersionRead"];

export type ChunkingConfigurationExpanded = components["schemas"]["ChunkingConfigurationExpanded"];
export type ChunkingConfigurationComposed = components["schemas"]["ChunkingConfigurationComposed"];
export type ChunkingConfigurationCoverage = components["schemas"]["ChunkingConfigurationCoverage"];
export type ChunkingConfigurationCompose = components["schemas"]["ChunkingConfigurationCompose"];
export type ParsingProfileRead = components["schemas"]["ParsingProfileRead"];
export type ChunkingProfileRead = components["schemas"]["ChunkingProfileRead"];
export type EmbeddingProfileRead = components["schemas"]["EmbeddingProfileRead"];
export type EmbeddingProfileCreate = components["schemas"]["EmbeddingProfileCreate"];
export type EmbeddingProfileCreated = components["schemas"]["EmbeddingProfileCreated"];
export type VectorStoreProfileRead = components["schemas"]["VectorStoreProfileRead"];
export type VectorStoreProfileCreate = components["schemas"]["VectorStoreProfileCreate"];
export type VectorStoreProfileCreated = components["schemas"]["VectorStoreProfileCreated"];

export type RetrievalProfileRead = components["schemas"]["RetrievalProfileRead"];
export type RetrievalStrategy = components["schemas"]["RetrievalStrategy"];
export type RetrievalProfileCreate = components["schemas"]["RetrievalProfileCreate"];
export type RetrievalProfileCreated = components["schemas"]["RetrievalProfileCreated"];
export type RetrieveRequest = components["schemas"]["RetrieveRequest"];
export type RetrieveResponse = components["schemas"]["RetrieveResponse"];
export type RetrievedHitRead = components["schemas"]["RetrievedHitRead"];

export type IndexBuildRead = components["schemas"]["IndexBuildRead"];
export type IndexBuildDetail = components["schemas"]["IndexBuildDetail"];
export type IndexBuildCreate = components["schemas"]["IndexBuildCreate"];
export type IndexBuildCreated = components["schemas"]["IndexBuildCreated"];
export type IndexBuildAccepted = components["schemas"]["IndexBuildAccepted"];

export type MaterializationAccepted = components["schemas"]["MaterializationAccepted"];
export type MaterializationDetail = components["schemas"]["MaterializationDetail"];
export type MaterializationRead = components["schemas"]["MaterializationRead"];
export type MaterializationProgress = components["schemas"]["MaterializationProgress"];
export type DocumentFailureRead = components["schemas"]["DocumentFailureRead"];

export type ChunkRead = components["schemas"]["ChunkRead"];
export type ChunkResultRead = components["schemas"]["ChunkResultRead"];
export type DocumentChunksRead = components["schemas"]["DocumentChunksRead"];
export type ChunkComparisonRead = components["schemas"]["ChunkComparisonRead"];
export type DocumentParseRead = components["schemas"]["DocumentParseRead"];
export type ParsePageRead = components["schemas"]["ParsePageRead"];

export type QASetRead = components["schemas"]["QASetRead"];
export type QASetCreate = components["schemas"]["QASetCreate"];
export type QASetDetail = components["schemas"]["QASetDetail"];
export type QASetSnapshotRead = components["schemas"]["QASetSnapshotRead"];
export type QASetSnapshotCreated = components["schemas"]["QASetSnapshotCreated"];
export type QuestionRead = components["schemas"]["QuestionRead"];
export type ImportSummaryRead = components["schemas"]["ImportSummaryRead"];

export type ExperimentRead = components["schemas"]["ExperimentRead"];
export type ExperimentDetail = components["schemas"]["ExperimentDetail"];
export type ExperimentCreate = components["schemas"]["ExperimentCreate"];
export type VariantCreate = components["schemas"]["VariantCreate"];
export type VariantRead = components["schemas"]["VariantRead"];
export type CoverageRead = components["schemas"]["CoverageRead"];
export type RunRead = components["schemas"]["RunRead"];
export type RunDetail = components["schemas"]["RunDetail"];
export type RunAccepted = components["schemas"]["RunAccepted"];
export type RunResultsRead = components["schemas"]["RunResultsRead"];
export type VariantResultRead = components["schemas"]["VariantResultRead"];
export type MetricResultRead = components["schemas"]["MetricResultRead"];
export type RunQuestionRead = components["schemas"]["RunQuestionRead"];
export type QuestionDrilldownRead = components["schemas"]["QuestionDrilldownRead"];
export type VariantDrilldownRead = components["schemas"]["VariantDrilldownRead"];
export type HitDetailRead = components["schemas"]["HitDetailRead"];
export type QuestionVariantOutcomeRead = components["schemas"]["QuestionVariantOutcomeRead"];

export type Page<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};

export type FileOutcome = "imported" | "skipped_duplicate" | "skipped_unsupported" | "failed";

export type DocumentStatus = "pending" | "fetching" | "stored" | "failed";
export type ArtifactStatus = "pending" | "running" | "ready" | "failed";
