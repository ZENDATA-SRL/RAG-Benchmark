# Temporal worker

Durable execution of everything that cannot run inside an HTTP request: parsing a 300-page
PDF, chunking a corpus, building an index. The package holds the workflows, their activities
and the **builtin component implementations**.

## Why the implementations are here and not in the backend

The worker is the only process that ever invokes a parser or a chunker. Keeping the code here
means the API image does not carry `pypdf` or `langchain-text-splitters`, and a change to an
extraction heuristic redeploys the worker alone.

What stays in the backend is the *declaration*:

| In `backend/src/components/builtin/` | In `temporal/components/` |
|---|---|
| `Parser` / `Chunker` protocols | classes implementing them |
| `ParseOutput`, `ChunkPayload` | — |
| descriptors: key, version, `params_schema`, `capabilities` | `BUILTIN_PARSERS`, `BUILTIN_CHUNKERS` |

The API must serve `params_schema` to render the UI forms (RT-U01) with no worker running, so
the schemas cannot live only here. Dependencies therefore flow **`temporal → backend`**; the
reverse would be a cycle, since the worker already imports `ArtefactService`, the object
storage and the session factory.

## The split's one risk, and its guard

Because the API declares components without importing their code, nothing at import time
notices a descriptor whose implementation was never written. Two checks close that gap:

- `assert_registry_complete()` runs at worker startup and fails loudly on a declared-but-
  unimplemented component. Boot time is the right place: an activity would discover it hours
  into a run.
- `tests/test_component_registry.py` asserts the correspondence in **both** directions and
  that each implementation satisfies its protocol.

## Layout

```
temporal/
  client.py         connect to the Temporal frontend with the shared data converter
  codec.py          SizeGuardCodec: rejects payloads over 128 KB (RT-O02), re-exported from the backend
  config.py         worker engine + `activity_session()` (one transaction per activity), data converter
  task_queues.py    ingestion / parsing / chunking / embedding queues (RT-O03)
  worker.py         one Worker per queue, registers all workflows and activities, asserts the registry
  workflow_ids.py   deterministic workflow ids (RT-O01), re-exported from the backend
  activities/       see below
  workflows/        see below
  components/
    __init__.py       BUILTIN_PARSERS / BUILTIN_CHUNKERS, resolve_*, assert_registry_complete
    parsers/          pypdf, plumber (pdfplumber), normalization, PermanentParsingError
    chunkers/         recursive, markdown, header_footer (page furniture), page_mapping (offset -> page)
    embedders/        shared.py: resolve_embedder(key, params) -> LangChain Embeddings
  tests/
```

## Workflows

All activities run in `activity_session()`: a dedicated engine and one transaction per
activity, outside any HTTP request. Workflow ids are deterministic (`workflow_ids.py`), so
launching the same work twice is rejected or reported instead of duplicated.

| Workflow | Does | Notes |
|---|---|---|
| `ProcessDocumentWorkflow` | `resolve_configuration` → `parse_document` → `chunk_document` for one document | A permanent parse failure returns `{status: "failed"}` instead of raising, so the parent can aggregate. Parsing heartbeats every few seconds (2 min heartbeat timeout, 30 min budget) |
| `MaterializeChunksWorkflow` | Opens a `materialization_runs` row, finds the documents that still need chunking, runs one `ProcessDocumentWorkflow` child each (default concurrency 5), records progress, summarises | `continue_as_new` every 500 documents (RT-O05). Re-running a finished set finds everything cached and does no parsing |
| `IndexCorpusWorkflow` | Resolves the index build, runs `MaterializeChunksWorkflow` as a child over the snapshot's documents, then embeds the chunks in batches of 100 and marks the build `ready` | Fails the build with `chunk_materialization_failed` if any document failed. `continue_as_new` every 100 batches, carrying offset and embedded count. **Does not yet upsert into the vector store** |

## Activities

| Module | Activities | Queue |
|---|---|---|
| `reads.py` | `resolve_configuration`; helpers `load_parsing_component`, `load_chunking_component`, `load_embedder_component` that return `(component key, params)` | parsing |
| `parsing.py` | `parse_document`: claim the parse (cache hit returns at once), download, validate params, run the parser in a thread while heartbeating, write `parses/{config_hash}/{content_hash}.json`, complete the artefact | parsing |
| `chunking.py` | `chunk_document`: claim the chunk result, read the parse from storage, run the chunker, write the `chunks` rows. Clears orphan chunks left by a failed attempt | chunking |
| `materialization.py` | `open_materialization_run`, `documents_needing_chunking`, `record_progress`, `summarize_run` | chunking |
| `indexing.py` | `resolve_index_build`, `open_index_build`, `count_index_chunks`, `fetch_index_chunk_batch`, `complete_index_build` | chunking |
| `embed.py` | `embed_batch`: validate params, embed the texts, write `embeddings/{index_build_id}/{batch_offset}.json` to object storage | embedding |

Large artefacts never travel through Temporal: parse output and embeddings go to object
storage and only their URI is passed around, which is what the 128 KB payload guard enforces.

## Builtin components

| Type | Keys | Notes |
|---|---|---|
| parser | `pypdf`, `pdfplumber` | Text is normalised (ligatures, smart quotes) so lexical retrieval matches. No text to extract, corrupt or encrypted raises `PermanentParsingError` |
| chunker | `recursive`, `markdown` | Document-scoped. Page headers/footers are stripped before splitting; each chunk records the page span it covers |
| embedder | `openai`, `bedrock` | Built on LangChain `Embeddings`; model and credentials come from the profile params |

## Known gaps

- `assert_registry_complete()` checks parsers and chunkers only. Embedders are resolved by a
  key switch in `embedders/shared.py`, so a declared embedder without a branch fails at the
  first `embed_batch`, not at boot.
- The `chromadb` vector store is declared in the backend but has no implementation here, no
  activity writes to it, and the embedding vectors are left in object storage.
- Embedder credentials are read from profile params, which are stored in the database; this
  conflicts with RT-S01 (credentials never in the database) and needs a secret reference.

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
