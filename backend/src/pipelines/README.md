# pipelines

Everything between a stored document and an index: profiles, configurations, per-document
artefacts, materialisation runs and index builds.

## Entities (`models.py`)

| Entity | Identity |
|---|---|
| `ParsingProfile`, `ChunkingProfile`, `EmbeddingProfile`, `VectorStoreProfile`, `RetrievalProfile` | `config_hash` = component version + canonical params |
| `ChunkingConfiguration` | Parsing profile + chunking profile; the unit of comparability |
| `ParsingResult` | `cache_key` = document content hash + parsing profile hash; output on object storage |
| `ChunkResult`, `Chunk` | `cache_key` = document content hash + configuration hash; chunks are rows |
| `IndexBuild` | `chain_fingerprint` over snapshot, configuration, embedding and vector store |
| `MaterializationRun` | One user-triggered run: progress counters and failures |

Artefact status is `pending → running → ready | failed` (`ArtifactStatus`).

## Services (`service.py`)

`ProfileService`, `ChunkingConfigurationService`, `ArtefactService`,
`MaterializationRunService`, `MaterializationService`, `IndexBuildService`,
`IndexCorpusService`, `InspectionService`. `ArtefactService` is the one the worker calls: its
`claim_*` methods return a cached `ready` artefact or a fresh `pending` row, which is what
makes re-running a materialisation cheap.

## Starting workflows

`MaterializationService.start` and `IndexCorpusService.start` launch Temporal workflows
through the `WorkflowClient` protocol with ids from `workflow_ids.py`. If a workflow with the
same id is already running, the call reports it instead of starting another.

## Routes (`router.py`)

Profiles (`/parsing-profiles`, `/chunking-profiles`, `/embedding-profiles`),
`/chunking-configurations` (including `/compose` and `/{id}/coverage`),
`/materializations` (start, list, detail, cancel), `/index-builds` (create, `/{id}/start`),
and inspection (`/documents/{id}/chunks`, `/chunk-results`, `/chunks/{id}`,
`/documents/{id}/parse`).

`exceptions.py` has one error per failure the UI must tell apart, such as
`ParsingProfileMismatchError`, `EmptyMaterializationError`, `MaterializationNotCancellableError`.
