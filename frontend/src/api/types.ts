import type { components } from "./schema";

export type CorpusRead = components["schemas"]["CorpusRead"];
export type CorpusCreate = components["schemas"]["CorpusCreate"];
export type CorpusUpdate = components["schemas"]["CorpusUpdate"];
export type CorpusProgress = components["schemas"]["CorpusProgress"];
export type CorpusDocumentRemoved = components["schemas"]["CorpusDocumentRemoved"];

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

export type Page<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};

export type FileOutcome =
  | "imported"
  | "skipped_duplicate"
  | "skipped_unsupported"
  | "failed";

export type DocumentStatus = "pending" | "fetching" | "stored" | "failed";
export type ArtifactStatus = "pending" | "running" | "ready" | "failed";
