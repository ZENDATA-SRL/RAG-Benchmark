# Temporal worker

Durable execution of everything that cannot run inside an HTTP request: parsing a 300-page
PDF, chunking a corpus, building an index. The package holds the workflows, their activities
and the **builtin component implementations**.

## Why the implementations are here and not in the backend

The worker is the only process that ever invokes a parser or a chunker, or writes a vector
store. Keeping that code here means the API image does not carry `pypdf` or
`langchain-text-splitters`, and a change to an extraction heuristic redeploys the worker
alone.

What stays in the backend is the *declaration*, plus the code the API runs as well:

| In `backend/src/components/builtin/` | In `backend/src/retrieval/` | In `temporal/components/` |
|---|---|---|
| `Parser` / `Chunker` / `VectorStoreReader` protocols | — | parser and chunker classes |
| `ParseOutput`, `ChunkPayload`, `VectorHit` | — | — |
| descriptors: key, version, `params_schema`, `capabilities` | `BUILTIN_EMBEDDERS`, `BUILTIN_VECTOR_STORE_READERS`, distance mapping | `BUILTIN_PARSERS`, `BUILTIN_CHUNKERS`, `BUILTIN_VECTOR_STORES` (writers) |

Embedders and readers live in the backend because retrieval runs in the API: a query is
synchronous and called many times per question, so it does not go through a workflow. The
worker imports the same embedders, so a query is embedded by exactly the code that embedded
its index, and its writers use the same distance mapping as the readers.

The API must serve `params_schema` to render the UI forms with no worker running, so
the schemas cannot live only here. Dependencies therefore flow **`temporal → backend`**; the
reverse would be a cycle, since the worker already imports `ArtefactService`, the object
storage and the session factory.

## The split's one risk, and its guard

Because the API declares components without importing their code, nothing at import time
notices a descriptor whose implementation was never written. Two checks close that gap:

- `assert_registry_complete()` runs at worker startup and fails loudly on a declared-but-
  unimplemented component, or a vector store with no reader (an index the API could not
  query). Boot time is the right place: an activity would discover it hours into a run.
- `tests/test_component_registry.py` asserts the correspondence in **both** directions and
  that each implementation satisfies its protocol.

## Layout

```
temporal/
  client.py         connect to the Temporal frontend with the shared data converter
  codec.py          SizeGuardCodec: rejects payloads over 128 KB, re-exported from the backend
  config.py         worker engine + `activity_session()` (one transaction per activity), data converter
  task_queues.py    ingestion / parsing / chunking / embedding / experiments queues
  worker.py         one Worker per queue, registers all workflows and activities, asserts the registry
  workflow_ids.py   deterministic workflow ids, re-exported from the backend
  activities/       see below
  workflows/        see below
  components/
    __init__.py       BUILTIN_PARSERS / BUILTIN_CHUNKERS / BUILTIN_VECTOR_STORES, resolve_*, assert_registry_complete
    parsers/          pypdf, plumber (pdfplumber), normalization, PermanentParsingError
    chunkers/         recursive, markdown, header_footer (page furniture), page_mapping (offset -> page)
    vector_stores/    chroma.py, qdrant.py: ChromaVectorStore, QdrantVectorStore (collection per index build, upsert by chunk id)
  tests/
```

## Workflows

All activities run in `activity_session()`: a dedicated engine and one transaction per
activity, outside any HTTP request. Workflow ids are deterministic (`workflow_ids.py`), so
launching the same work twice is rejected or reported instead of duplicated.

| Workflow | Does | Notes |
|---|---|---|
| `ProcessDocumentWorkflow` | `resolve_configuration` → `parse_document` → `chunk_document` for one document | A permanent parse failure returns `{status: "failed"}` instead of raising, so the parent can aggregate. Parsing heartbeats every few seconds (2 min heartbeat timeout, 30 min budget) |
| `MaterializeChunksWorkflow` | Opens a `materialization_runs` row, finds the documents that still need chunking, runs one `ProcessDocumentWorkflow` child each (default concurrency 5), records progress, summarises | Takes a list of document ids or a corpus snapshot, paged 500 ids at a time. `continue_as_new` every 500 documents. Re-running a finished set finds everything cached and does no parsing |
| `RunExperimentWorkflow` | Opens the run, runs one `RunVariantWorkflow` child per variant one after the other, then scores what did not succeed, aggregates the metrics and closes the run | A failure of the run itself is recorded on it (`fail_experiment_run`) before the workflow fails, so it does not stay `running` |
| `RunVariantWorkflow` | Pages through the executions of one variant that did not succeed (a cursor on the id), runs `retrieve_question` for each with bounded concurrency, records progress after every page of 100 | An activity that keeps failing (4 attempts with backoff) marks only its execution `failed` and the run goes on. `continue_as_new` every 5 pages. A relaunched run redoes only the executions that did not succeed |
| `IndexCorpusWorkflow` | Resolves the index build, runs `MaterializeChunksWorkflow` as a child over the snapshot, creates the vector store collection, then for each batch of 100 chunks embeds to object storage and upserts into the collection, and marks the build `ready` | Fails the build with `chunk_materialization_failed` if any document failed, and marks it `failed` if an activity fails for good. `continue_as_new` every 100 batches, carrying offset and counters only |

## Activities

| Module | Activities | Queue |
|---|---|---|
| `reads.py` | `resolve_configuration`; helpers `load_parsing_component`, `load_chunking_component`, `load_embedder_component`, `load_vector_store_component` that return `(component key, params)` | parsing |
| `parsing.py` | `parse_document`: claim the parse (cache hit returns at once), download, validate params, run the parser in a thread while heartbeating, write `parses/{config_hash}/{content_hash}.json`, complete the artefact | parsing |
| `chunking.py` | `chunk_document`: claim the chunk result, read the parse from storage, run the chunker, write the `chunks` rows. Clears orphan chunks left by a failed attempt | chunking |
| `materialization.py` | `open_materialization_run`, `documents_needing_chunking`, `snapshot_documents_needing_chunking` (one page of a snapshot), `record_progress`, `summarize_run` | chunking |
| `indexing.py` | `resolve_index_build`, `open_index_build`, `count_index_chunks`, `complete_index_build` | chunking |
| `embed.py` | `embed_batch`: read one page of the build's chunks, embed them, check the profile's `dimensions`, write `embeddings/{index_build_id}/{batch_offset}.json` (vector, text, document, ordinal) to object storage | embedding |
| `vector_store.py` | `prepare_index_collection` (create the collection with the profile's index params), `upsert_embedding_batch` (read the batch file, upsert into the collection) | embedding |
| `experiments.py` | `open_experiment_run`, `list_unfinished_executions` (one page after a cursor), `retrieve_question` (search in-process through `RetrievalService`, record the hits, score the execution), `mark_execution_failed`, `record_run_progress`, `finish_experiment_run`, `fail_experiment_run` | experiments |

Large artefacts never travel through Temporal: parse output and embeddings go to object
storage and only their URI is passed around, which is what the 128 KB payload guard enforces.

## Builtin components

| Type | Keys | Notes |
|---|---|---|
| parser | `pypdf`, `pdfplumber` | Text is normalised (ligatures, smart quotes) so lexical retrieval matches. No text to extract, corrupt or encrypted raises `PermanentParsingError` |
| chunker | `recursive`, `markdown` | Document-scoped. Page headers/footers are stripped before splitting; each chunk records the page span it covers |
| embedder | `openai`, `bedrock` | Built on LangChain `Embeddings`, imported from `backend/src/retrieval/embedders.py`; model and credentials come from the profile params or the environment |
| vector store | `chromadb` | HTTP client to the `chromadb` compose service; one collection per index build, configured from the profile's space and HNSW params |
| vector store | `qdrant` | Client to the `qdrant` compose service; one collection per index build, created at the first batch with the profile's distance and HNSW params |

A profile without `space` is indexed with `cosine` on both stores (the shared default of
`backend/src/retrieval/distances.py`), not with each engine's own default.

## Known gaps

- A build re-run reuses its collection as it is: the HNSW configuration is applied only
  when the collection is created, so changing it means a new vector store profile (and
  therefore a new build).
- `MaterializeChunksWorkflow` started by list (`POST /materializations`) still carries the
  document ids in its input; for corpora of a few thousand documents that path can exceed
  the payload limit. Index builds use the snapshot path and are not affected.
- Embedder credentials *can* still be typed into profile params, which are stored in the
  database; this conflicts with the rule that credentials never live in the database. Leave them empty
  and use the credentials below instead.

## AWS credentials (Bedrock)

The worker container mounts the host's `~/.aws` read-only at `/aws` and selects a profile
with `AWS_PROFILE`, so boto3 resolves credentials exactly as it does on the host and no key
is written in `docker-compose.yml` or `.env`:

| Variable (in `.env`) | Default | Meaning |
|---|---|---|
| `AWS_CONFIG_DIR` | `~/.aws` | Host directory mounted into the worker |
| `WORKER_AWS_PROFILE` | `default` | Profile the worker uses |

The region comes from the embedding profile's `region` param when set, otherwise from the AWS
profile; leave the param empty to use the profile's region. After changing the profile,
recreate the worker: `docker compose --profile worker up -d worker`. The mount gives the
worker read access to every profile in that directory; point `AWS_CONFIG_DIR` at a
dedicated directory to expose fewer.

## Running outside Docker

Neither `temporal` nor `src` is an installed package: both source roots have to be on
`PYTHONPATH`, since here there is no `pythonpath` (pytest) nor `prepend_sys_path` (alembic) to
supply them. From the repository root:

```bash
PYTHONPATH=.:backend uv run python -m temporal.worker
```

## Tests

Run from the repository root, since `pythonpath` covers both source roots:

```bash
uv run pytest temporal/tests
```
