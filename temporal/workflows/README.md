# workflows

Deterministic orchestration only: no I/O, no randomness, no imports of heavy libraries
(activity and backend imports go inside `workflow.unsafe.imports_passed_through()`).
`__init__.py` exposes `ALL_WORKFLOWS` for the worker.

| Workflow | Input | Calls |
|---|---|---|
| `ProcessDocumentWorkflow` | document id, chunking configuration id | `resolve_configuration` → `parse_document` → `chunk_document`. Returns `{status: "failed", reason: "parse_failed"}` rather than raising when the parse fails permanently |
| `MaterializeChunksWorkflow` | `MaterializeInput` (document ids, configuration id, optional corpus id, concurrency) | `open_materialization_run`, `documents_needing_chunking`, then one `ProcessDocumentWorkflow` child per document that needs it (default concurrency 5), `record_progress`, `summarize_run`. `continue_as_new` after 500 documents, carrying counters so the denominator never shifts |
| `IndexCorpusWorkflow` | `IndexCorpusInput` (or just an index build id) | `resolve_index_build`, `open_index_build`, child `MaterializeChunksWorkflow`, `count_index_chunks`, then a loop of `fetch_index_chunk_batch` + `embed_batch` (100 chunks per batch), `complete_index_build`. `continue_as_new` every 100 batches |

## Ids and idempotency

Workflow ids come from `src/infrastructure/temporal/workflow_ids.py`, deterministic in what the workflow
does (configuration + document set; index build id). The API computes the same id when it
starts a workflow, so a duplicate launch is detected by Temporal itself.

## Timeouts

Parse 30 min with a 2 min heartbeat timeout, chunk 15 min, embed batch 15 min, reads 30 s,
`MaterializeChunksWorkflow` child 2 h inside indexing. Retries: 3 attempts, and
`PermanentParsingError` is non-retryable.

## Current limit

`IndexCorpusWorkflow` ends after embedding. Nothing yet upserts the vectors into the vector
store, and a build is marked `ready` once the vectors are on object storage.
