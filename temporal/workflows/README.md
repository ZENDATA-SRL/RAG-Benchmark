# workflows

Deterministic orchestration only: no I/O, no randomness, no imports of heavy libraries
(activity and backend imports go inside `workflow.unsafe.imports_passed_through()`).
`__init__.py` exposes `ALL_WORKFLOWS` for the worker.

| Workflow | Input | Calls |
|---|---|---|
| `ProcessDocumentWorkflow` | document id, chunking configuration id | `resolve_configuration` → `parse_document` → `chunk_document`. Returns `{status: "failed", reason: "parse_failed"}` rather than raising when the parse fails permanently |
| `MaterializeChunksWorkflow` | `MaterializeInput` (document ids **or** a corpus snapshot id with its `total`, configuration id, optional corpus id, concurrency) | `open_materialization_run`, `documents_needing_chunking` (or `snapshot_documents_needing_chunking`, 500 ids per page, the offset carried by `continue_as_new`), then one `ProcessDocumentWorkflow` child per document that needs it (default concurrency 5), `record_progress`, `summarize_run`. `continue_as_new` after 500 documents, carrying counters so the denominator never shifts |
| `IndexCorpusWorkflow` | `IndexCorpusInput` (or just an index build id) | `resolve_index_build`, `open_index_build`, child `MaterializeChunksWorkflow` over the snapshot, `count_index_chunks`, `prepare_index_collection`, then a loop of `embed_batch` + `upsert_embedding_batch` (100 chunks per batch), `complete_index_build`. `continue_as_new` every 100 batches. An activity or child failing for good marks the build `failed` before the workflow fails |

## Ids and idempotency

Workflow ids come from `src/infrastructure/temporal/workflow_ids.py`, deterministic in what the workflow
does (configuration + document set; index build id). The API computes the same id when it
starts a workflow, so a duplicate launch is detected by Temporal itself. An index build
derives the id of its materialisation from the snapshot's `composition_hash`
(`materialize_workflow_id_for_composition`), which is the same id a launch by list of the
same documents gets.

## Timeouts

Parse 30 min with a 2 min heartbeat timeout, chunk 15 min, embed batch 15 min, collection
and upsert 5 min, reads 30 s,
`MaterializeChunksWorkflow` child 2 h inside indexing. Retries: 3 attempts, and
`PermanentParsingError` is non-retryable.

## Payload size

Workflow inputs carry ids, offsets and counters only: the snapshot's documents are paged by
an activity and the chunk texts are read by `embed_batch` itself, so neither grows the
payload with the corpus. `tests/test_index_corpus.py` runs the indexing with the size guard
lowered to 32 KB and a 1200-document snapshot to keep it that way.
