# Backend

FastAPI service that owns the data model, serves the HTTP API and *starts* Temporal
workflows. It never executes a parser or a chunker, and never writes a vector store: that is
the worker's job (see [`../temporal/README.md`](../temporal/README.md)). The one exception is
retrieval: the API embeds the query and reads the vector store itself, because the retrieval
tool is synchronous and called many times per question (see `retrieval/` below).

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
| `main.py` | App factory, request-id middleware, `DomainError` → HTTP handler, router registration; the lifespan seeds the builtin registry, the `upload` source and the metric catalog |
| `settings.py` | `Settings` read from `.env` (database, object storage, Temporal, ChromaDB and Qdrant addresses for the worker and for retrieval, upload limits, CORS) |
| `dependencies.py` | FastAPI dependencies for object storage and the workflow client |
| `core/` | `hashing`, `get_or_create`, domain errors (`NotFoundError`, `ConflictError`, `ValidationError`, `UnsupportedOperationError`), `Page` pagination, logging with request id |
| `infrastructure/database/` | Declarative `Base` + mixins (UUID pk, `created_at`, `updated_at`), PostgreSQL enums, async session |
| `infrastructure/storage/` | `ObjectStorage` protocol, S3/MinIO implementation, key helpers (`document_key`, `parse_key`) |
| `infrastructure/temporal/` | `WorkflowClient` protocol (`start`, `cancel`) and its Temporal implementation, `SizeGuardCodec` (payloads over 128 KB are rejected), and `workflow_ids.py` (workflow names, task queues, deterministic ids) |
| `components/` | Registry of pluggable components, see below |
| `documents/` | Upload, content-hash deduplication, provenance, metadata, content download |
| `corpora/` | Corpora, their documents, progress, and immutable snapshots |
| `sources/` | Source connections and import runs; today only the built-in `upload` source |
| `pipelines/` | Profiles and chunking configurations: the configuration side, nothing executed |
| `artifacts/` | Per-document parsing and chunking results, chunks, coverage and inspection |
| `materializations/` | User-triggered chunk materialisation runs and their progress |
| `indexes/` | Index builds over a corpus snapshot, and launching their indexing |
| `retrieval/` | Dense search over a ready index build; the embedders and vector store readers shared with the worker |
| `qa_sets/` | Question sets: authoring of questions, gold documents, expected answers, evidence chunks confirmed per chunking configuration, CSV/JSONL import and export, immutable snapshots |
| `experiments/` | Retrieval experiments: variants, guards, runs on Temporal, document- and chunk-level metrics, re-evaluation, results grouped by chunking configuration |

The pipeline modules depend on each other in one direction only:

```
pipelines ← artifacts ← materializations
          ↖ indexes ← retrieval ← experiments → qa_sets
```

`retrieval` also reads `experiments.repository` to record the calls of an execution.

### `components/`

A component is a `components` row (type + key) with one or more `component_versions`
carrying `params_schema` (JSON Schema) and `capabilities`. `ComponentService.validate_params`
checks a profile's params against the schema of its version.

- `GET /components` — components with their versions and schemas; drives the UI forms.
- `GET /components/{id}/versions` — the versions of one component.
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
  | vector store | `chromadb`, `qdrant` |

  `contracts.py` holds the `Parser`/`Chunker`/`VectorStoreReader` protocols and the
  `ParseOutput`/`ChunkPayload`/`VectorHit` shapes. Parsers, chunkers and vector store writers
  are implemented in `temporal/components/`, so the API carries no parsing library; embedders
  and vector store readers are in `retrieval/`, because the API runs them too.

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
| `POST/GET /corpora/{id}/snapshots`, `GET …/{snapshot_id}`, `GET …/{snapshot_id}/documents` | Freeze a selection (without `document_ids`: every `stored` document), idempotent by composition and answering `created`; list and read snapshots |

### `pipelines/`

Configuration only. `ProfileService` does get-or-create for parsing, chunking, embedding,
vector-store and retrieval profiles: a profile is `component_version + params`, params are
validated against the version's schema, and chunkers must declare
`capabilities.scope = document`. A retrieval profile has no component version; its API
exposes `strategy` (a `retrieval_strategy` enum, of which only `dense` is accepted, the
others answering `422`), `top_k` and `score_threshold`. The reranker,
MMR and fusion columns stay in the model, empty, for when the engine applies them. Query
transformations are not a retrieval setting: they belong to the answer system, and neither
are filters on documents: the corpus snapshot fixes what is searched. `ChunkingConfigurationService` pairs a parsing profile with
a chunking profile (a **chunking configuration**, the unit of comparability) and offers
`compose`, which builds both profiles and the configuration from one form.

| Route | Purpose |
|---|---|
| `POST/GET /parsing-profiles`, `/chunking-profiles`, `/embedding-profiles`, `/vector-store-profiles`, `/retrieval-profiles`; `GET …/{id}` | Profiles |
| `POST /chunking-configurations`, `GET …`, `GET …/{id}` | Configurations |
| `POST /chunking-configurations/compose` | Create both profiles and the configuration in one call (single UI form) |

### `artifacts/`

`ArtefactService` — `claim_*` / `complete_*` / `fail_artefact` for `parsing_results` and
`chunk_results`. A `ready` artefact with the same `cache_key` is returned as is, which is
how materialisation skips work already done. Used by the worker's activities.
`CoverageService` counts how many documents of a corpus a configuration has chunked;
`InspectionService` reads chunks, chunk results and per-page parse output.

| Route | Purpose |
|---|---|
| `GET /chunking-configurations/{id}/coverage` | How far a configuration is materialised over a corpus |
| `GET /documents/{id}/chunks`, `GET /documents/{id}/chunks/compare`, `GET /chunk-results`, `GET /chunks/{id}`, `GET /documents/{id}/parse` | Inspect artefacts |

### `materializations/`

`MaterializationService` starts (or reuses) a `MaterializeChunksWorkflow` and cancels it;
`MaterializationRunService` keeps the `materialization_runs` progress row the UI polls.

| Route | Purpose |
|---|---|
| `POST /materializations`, `GET /materializations[/{id}]`, `POST …/{id}/cancel` | Materialise chunks for a configuration over documents or a corpus |

### `indexes/`

`IndexBuildService` creates an index build (idempotent by `chain_fingerprint`), reads and
lists builds; `IndexCorpusService` launches `IndexCorpusWorkflow`.

| Route | Purpose |
|---|---|
| `POST /index-builds`, `POST /index-builds/{id}/start` | Create and start indexing; `202` with `started=false` if the same work is already running |
| `GET /index-builds[?corpus_snapshot_id=]`, `GET /index-builds/{id}` | List builds; read one with its status and `chunk_count` |

### `retrieval/`

`RetrievalService.search` answers a query against a `ready` index build (`409` otherwise)
with dense search, the only strategy a profile can have: it embeds the query with the
**build's** embedding profile, asks the vector store for the `top_k` neighbours among the
build's chunks, applies `score_threshold`, and enriches each hit from the
database with chunk, document, filename, ordinal, page and text. A vector whose chunk no
longer exists comes back with a null `chunk_id` instead of failing the query; an embedder or
vector store failure is a `502` naming the stage.

Scores are normalised so that higher is better on every store and space: cosine and inner
product are similarities, Euclidean distance `d` becomes `1 / (1 + d)`. The mapping lives in
`distances.py` and is shared with the worker's writers, which also apply the same default
space (`cosine`) when a profile declares none.

| Route | Purpose |
|---|---|
| `POST /retrieve` | `{index_build_id, retrieval_profile_id, query, execution_id?}` → `{hits: [{rank, score, stage, chunk_id, document_id, filename, ordinal, page, text}], timings, corpus_id, chunking_configuration_id}` |

With an `execution_id` the call and its hits are recorded against that experiment execution
(`404` if it does not exist); without one the call is only logged.

### `qa_sets/`

Question sets, their gold documents, expected answers, evidence chunks and snapshots.
`POST /qa-sets/{id}/import`
reads a CSV or JSONL (`question`, `answer`, `gold_files`, `tags`, `answerable`), resolves the
files by name or hash
among the documents of the set's origin corpus and reports every row (imported, already
present, unresolved, ambiguous, invalid) without dropping any; `GET /qa-sets/{id}/export`
writes the same format back. Questions are also written one by one
(`POST /qa-sets/{id}/questions`), edited until a snapshot holds them and replaced afterwards
(`/questions/{id}`, `/questions/{id}/replace`). `PUT /questions/{id}/evidence` records which
chunks of a chunking configuration hold the answer (a draft, confirmed, or not found), and
confirming adds their documents to the gold documents. `POST /qa-sets/{id}/snapshots`
freezes the questions, deduplicated by composition. See [`src/qa_sets/README.md`](src/qa_sets/README.md).

### `experiments/`

| Route | Purpose |
|---|---|
| `POST /experiments`, `GET /experiments[/{id}]`, `GET /experiments/coverage` | Create an experiment (guards: variants on the experiment's corpus snapshot; an explicit choice for questions whose gold documents are not in it), list and read (each naming its corpus and QA set), check coverage |
| `POST /experiments/{id}/runs`, `GET …/runs/{run_id}`, `POST …/runs/{run_id}/cancel`, `POST …/runs/{run_id}/resume` | Launch a run on Temporal, poll it, cancel it, relaunch it redoing only what did not succeed |
| `POST …/runs/{run_id}/evaluate` | Re-score a finished run from its stored hits on the evidence as it is now, recording the fingerprint of that evidence |
| `GET …/runs/{run_id}/results[.csv]`, `GET …/runs/{run_id}/questions[/{question_id}]` | Document- and chunk-level metrics per variant, grouped by chunking configuration, with effective and excluded counts per reason, and the per-question drill-down |

Metrics, guards and the run lifecycle are described in [`src/experiments/README.md`](src/experiments/README.md).

### Data tables

`parsing_profiles`, `chunking_profiles`, `embedding_profiles`, `vector_store_profiles`,
`retrieval_profiles`, `parsing_results`, `chunking_configurations`, `chunk_results`,
`chunks`, `index_builds`, `materialization_runs`, `qa_sets`, `questions`, `expected_answers`, `gold_documents`,
`evidence_links`, `evidence_link_chunks`, `qa_set_snapshots`, `qa_snapshot_questions`, `experiments`, `variants`, `runs`, `executions`,
`retrieval_calls`, `retrieval_hits`, `metric_definitions`, `evaluators`, `evaluations`,
`metric_aggregates`. Profiles and configurations are in
`pipelines/models.py`, results and chunks in `artifacts/models.py`, runs in
`materializations/models.py`, index builds in `indexes/models.py`, the question sets in
`qa_sets/models.py` and the experiment tables in `experiments/models.py`.
Parse output lives on object storage and is referenced by `parsing_results.output_uri`;
chunks are rows. The full schema and its rationale are in
[`../docs/DATA_MODEL.md`](../docs/DATA_MODEL.md).

## Indexing flow

```
POST /corpora/{id}/snapshots          freeze the documents → CorpusSnapshot
POST /embedding-profiles              embedder + params (+ declared dimensions)
POST /vector-store-profiles           vector store + index params (space and HNSW for chromadb and qdrant)
POST /index-builds                    snapshot + chunking configuration + embedding + vector store
                                      → IndexBuild(pending), reused if the chain_fingerprint exists
POST /index-builds/{id}/start         → IndexCorpusWorkflow on the worker
GET  /index-builds/{id}               status: pending → running → ready | failed
POST /retrieval-profiles              strategy (dense only), top_k, score_threshold
POST /retrieve                        query a ready build → ranked chunks
```

The workflow materialises the chunks, embeds them in batches to object storage and upserts
each batch into a vector store collection (ChromaDB or Qdrant, as the vector store profile
says) named after the build's `external_index_ref`. What it does step by step is described in
the Temporal README.

## Experiment flow

```
POST /qa-sets                         a question set (optionally with its origin corpus)
POST /qa-sets/{id}/import             CSV/JSONL: question, answer, gold files, tags → summary of every row
POST /qa-sets/{id}/questions          or write the questions one by one
PUT  /questions/{id}/evidence         confirm the chunks that hold the answer, per chunking configuration
POST /qa-sets/{id}/snapshots          freeze the questions → QASetSnapshot (same questions, same snapshot)
POST /experiments                     corpus snapshot + QA snapshot + variants (index build × retrieval profile)
POST /experiments/{id}/runs           → RunExperimentWorkflow on the worker
GET  /experiments/{id}/runs/{run}     progress: pending → running → succeeded | failed
GET  /experiments/{id}/runs/{run}/results      document and chunk metrics per variant, grouped by chunking configuration, with n
POST /experiments/{id}/runs/{run}/evaluate     re-score after annotating, without retrieving again
GET  /experiments/{id}/runs/{run}/questions/{question}   what each variant retrieved, hit by hit
```
