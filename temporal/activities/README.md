# activities

Units of work the workflows call. Each opens its own transaction with `activity_session()`
(`temporal/config.py`) and touches the database through the backend services, so business
rules stay in one place.

Rules every activity follows:

- **Idempotent.** The artefact is *claimed* first (`ArtefactService.claim_*`): a `ready`
  result is returned as is, so a retry or a re-run does no work twice.
- **Small payloads.** Inputs and outputs are ids, offsets and URIs. Parse output and
  embeddings are written to object storage (RT-O02); the codec rejects anything over 128 KB.
  Lists that grow with the corpus (snapshot documents, chunk texts) are read by the
  activity that needs them, a page at a time, never passed in.
- **Blocking code off the event loop.** Parsers, chunkers and embedders run through
  `asyncio.to_thread`.
- **Params validated** against the component version's schema right before use.

| File | Activities | Task queue |
|---|---|---|
| `reads.py` | `resolve_configuration`; `load_parsing_component`, `load_chunking_component`, `load_embedder_component`, `load_vector_store_component` (return component key and effective params) | parsing |
| `parsing.py` | `parse_document`. Heartbeats every 15 s while the parser runs in a thread. A `PermanentParsingError` marks the result `failed` and returns normally | parsing |
| `chunking.py` | `chunk_document`. Deletes orphan chunks of a previously failed attempt before rewriting | chunking |
| `materialization.py` | `open_materialization_run`, `documents_needing_chunking`, `snapshot_documents_needing_chunking` (returns `{scanned, needing}` for one page of a snapshot), `record_progress`, `summarize_run` | chunking |
| `indexing.py` | `resolve_index_build` (ids, composition hash and document count, never the document list), `open_index_build`, `count_index_chunks`, `complete_index_build` | chunking |
| `embed.py` | `embed_batch(build, profile, offset, limit)`: reads the page of chunks, embeds it, writes `embeddings/{index_build_id}/{batch_offset}.json`. Vectors whose size differs from the profile's `dimensions` raise a non-retryable error | embedding |
| `vector_store.py` | `prepare_index_collection`, `upsert_embedding_batch(build, offset)`: reads the batch file and upserts it, keyed by chunk id | embedding |

`__init__.py` exposes `ALL_ACTIVITIES`, which the worker registers. A new activity must be
added there or the worker will not serve it.
