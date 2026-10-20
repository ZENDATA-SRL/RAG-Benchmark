# Backend

FastAPI service that owns the data model, serves the HTTP API and *starts* Temporal
workflows. It never executes a parser, a chunker or an embedder: that is the worker's job
(see [`../temporal/README.md`](../temporal/README.md)).

Module conventions and the dependency direction (`router → service → repository → models`)
are in the `backend-structure` skill ([`../.claude/skills/backend-structure/SKILL.md`](../.claude/skills/backend-structure/SKILL.md)).
Every route below is mounted under `/api/v1`.

## Core idea: everything is addressed by a hash

Artefacts are cached and deduplicated by the hash of what they are made of, so the same
inputs always resolve to the same row (`core/hashing.py`):

| Hash | Built from | Used by |
|---|---|---|
| `content_hash` | bytes of the file | `documents` |
| `config_hash` | component version id + canonical JSON params | the four profile tables |
| combined config hash | parsing + chunking profile hashes | `chunking_configurations` |
| `cache_key` | document `content_hash` + profile/configuration hash | `parsing_results`, `chunk_results` |
| `composition_hash` | sorted set of document ids | `corpus_snapshots` |
| `chain_fingerprint` | snapshot + chunking configuration + embedding + vector store | `index_builds` |

Creation goes through `core/get_or_create.py` (lookup, insert, recover from a unique
violation), which is why the "create" endpoints are idempotent and report whether the row
was `created` or reused.

## Modules

| Module | Responsibility |
|---|---|
| `main.py` | App factory, request-id middleware, `DomainError` → HTTP handler, router registration; the lifespan seeds the builtin registry and the `upload` source |
| `settings.py` | `Settings` read from `.env` (database, object storage, Temporal, upload limits, CORS) |
| `dependencies.py` | FastAPI dependencies for object storage and the workflow client |
| `core/` | `hashing`, `get_or_create`, domain errors (`NotFoundError`, `ConflictError`, `ValidationError`, `UnsupportedOperationError`), `Page` pagination, logging with request id |
| `infrastructure/database/` | Declarative `Base` + mixins (UUID pk, `created_at`, `updated_at`), PostgreSQL enums, async session |
| `infrastructure/storage/` | `ObjectStorage` protocol, S3/MinIO implementation, key helpers (`document_key`, `parse_key`) |
| `infrastructure/temporal/` | `WorkflowClient` protocol (`start`, `cancel`) and its Temporal implementation, plus `SizeGuardCodec` (payloads over 128 KB are rejected, RT-O02) |
| `components/` | Registry of pluggable components, see below |
| `documents/` | Upload, content-hash deduplication, provenance, metadata, content download |
| `corpora/` | Corpora, their documents, progress, and immutable snapshots |
| `sources/` | Source connections and import runs; today only the built-in `upload` source |
| `pipelines/` | Profiles, chunking configurations, per-document artefacts, materialisation and index builds |

### `components/`

A component is a `components` row (type + key) with one or more `component_versions`
carrying `params_schema` (JSON Schema) and `capabilities`. `ComponentService.validate_params`
checks a profile's params against the schema of its version.

- `GET /components` — components with their versions and schemas; drives the UI forms.
- `POST /components`, `POST /components/{id}/versions` — register custom components.
- `POST /components/versions/{id}/unavailable|available` — retire or restore a version.
- `registry_seed.py` — at every startup registers one row per descriptor in
  `builtin/__init__.py`, idempotently.
- `builtin/` — **declarations only**, one module per component exposing `KEY`, `VERSION`,
  `DISPLAY_NAME`, `PARAMS_SCHEMA`:

  | Type | Keys |
  |---|---|
  | parser | `pypdf`, `pdfplumber` |
  | chunker | `recursive`, `markdown` |
  | embedder | `openai`, `bedrock` |
  | vector store | `chromadb` |

  `contracts.py` holds the `Parser`/`Chunker` protocols and the `ParseOutput`/`ChunkPayload`
  shapes. The implementations are in `temporal/components/`, so the API image carries no
  parsing or embedding library.

### `documents/` and `sources/`

`DocumentService.ingest_upload[_batch]` spools the file while hashing it, rejects
unsupported MIME types (`Settings.allowed_mime_types`, PDF only for now), stores the bytes
at `documents/{content_hash}/{filename}` once, and records a `document_provenances` row for every
acquisition. Uploading the same file twice yields one document and two provenances.
Each batch is an `import_runs` row with one `import_file_results` per file
(`imported`, `skipped_duplicate`, `skipped_unsupported`, `failed`), handled by
`sources.UploadImportService`.

| Route | Purpose |
|---|---|
| `POST /documents/upload` | Upload one or more files |
| `GET /documents`, `GET /documents/{id}` | List / detail with provenances |
| `PATCH /documents/{id}/metadata` | Edit user metadata |
| `GET /documents/{id}/content` | Stream the original file |

### `corpora/`

A corpus is a mutable set of documents. A **snapshot** freezes that set
(`corpus_snapshots` + `corpus_snapshot_documents`, deduplicated by `composition_hash`) and
is what an index build searches over.

| Route | Purpose |
|---|---|
| `POST/GET /corpora`, `GET/PATCH/DELETE /corpora/{id}` | CRUD |
| `GET/POST /corpora/{id}/documents`, `DELETE …/{document_id}` | Membership |
| `POST /corpora/{id}/documents/upload` | Upload straight into a corpus |
| `GET /corpora/{id}/progress` | Documents per acquisition status |

### `pipelines/`

Services in `service.py`:

- `ProfileService` — get-or-create for parsing, chunking, embedding, vector-store and
  retrieval profiles. A profile is `component_version + params`, params validated against
  the version's schema; chunkers must declare `capabilities.scope = document`.
- `ChunkingConfigurationService` — a **chunking configuration** pairs a parsing profile with
  a chunking profile: the unit of comparability. Also `compose` (build one from two profile
  payloads) and `coverage` (how many documents are already chunked).
- `ArtefactService` — `claim_*` / `complete_*` / `fail_artefact` for `parsing_results` and
  `chunk_results`. A `ready` artefact with the same `cache_key` is returned as is, which is
  how materialisation skips work already done. Used by the worker's activities.
- `MaterializationService` / `MaterializationRunService` — start (or reuse) a
  `MaterializeChunksWorkflow`, cancel it, and keep the `materialization_runs` progress row.
- `IndexBuildService` / `IndexCorpusService` — create an index build and launch
  `IndexCorpusWorkflow`.
- `InspectionService` — read chunks, chunk results and per-page parse output.

`workflow_ids.py` computes the deterministic workflow ids (RT-O01). It lives here because the
API starts the workflows and must derive the same id the worker serves; the worker re-exports it.

| Route | Purpose |
|---|---|
| `POST/GET /parsing-profiles`, `/chunking-profiles`, `/embedding-profiles`; `GET …/{id}` for parsing and chunking | Profiles. `/vector-store-profiles` has a router but no routes yet; the service method `get_or_create_vector_store_profile` exists |
| `POST /chunking-configurations`, `GET …`, `GET …/{id}` | Configurations |
| `POST /chunking-configurations/compose` | Create both profiles and the configuration in one call (single UI form) |
| `GET /chunking-configurations/{id}/coverage` | How far a configuration is materialised over a corpus |
| `POST /materializations`, `GET /materializations[/{id}]`, `POST …/{id}/cancel` | Materialise chunks for a configuration over documents or a corpus |
| `POST /index-builds`, `POST /index-builds/{id}/start` | Create (idempotent by `chain_fingerprint`) and start indexing; `202` with `started=false` if the same work is already running |
| `GET /documents/{id}/chunks`, `GET /chunk-results`, `GET /chunks/{id}`, `GET /documents/{id}/parse` | Inspect artefacts |

### Data tables

`parsing_profiles`, `chunking_profiles`, `embedding_profiles`, `vector_store_profiles`,
`retrieval_profiles`, `parsing_results`, `chunking_configurations`, `chunk_results`,
`chunks`, `index_builds`, `materialization_runs` (all in `pipelines/models.py`).
Parse output lives on object storage and is referenced by `parsing_results.output_uri`;
chunks are rows. The full schema and its rationale are in
[`../docs/DATA_MODEL.md`](../docs/DATA_MODEL.md).

## Indexing flow

```
POST /index-builds        snapshot + chunking configuration + embedding + vector store
                          → IndexBuild(pending), reused if the chain_fingerprint exists
POST /index-builds/{id}/start
                          → IndexCorpusWorkflow on the worker
                          status: pending → running → ready | failed (no read endpoint yet)
```

What the workflow does is described in the Temporal README. Embedding is implemented;
writing the vectors into the vector store is not yet.
