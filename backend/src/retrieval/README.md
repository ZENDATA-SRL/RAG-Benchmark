# retrieval

Dense search over a ready index build: the engine behind `POST /retrieve`, the retrieval
tool answer systems will call. It runs in the API and not through a workflow, because a
query is synchronous, called many times per question, and has nothing to retry or resume.

This module also holds the component code both processes run, so the worker and the API
cannot drift apart:

| File | Role |
|---|---|
| `embedders.py` | `BUILTIN_EMBEDDERS` and `resolve_embedder(key, params)`: LangChain `Embeddings` for `openai` and `bedrock`. The worker embeds chunks with it, the API embeds queries with it |
| `distances.py` | The distance spaces (`cosine`, `l2`, `ip`), their Qdrant names, the default space applied by every writer, and the normalisation of raw distances into higher-is-better scores |
| `readers/` | `ChromaVectorStoreReader`, `QdrantVectorStoreReader` and `BUILTIN_VECTOR_STORE_READERS`. Each reads the space from the collection itself, so scores stay right for collections created before the shared default |
| `repository.py` | Component key of a profile's version, corpus of a snapshot, chunks by id with document and filename |
| `service.py` | `RetrievalService.search` |
| `schemas.py`, `router.py`, `exceptions.py` | `POST /retrieve`; `IndexBuildNotReadyError` (`409`), `RetrievalBackendError` (`502`, with the failing `stage`) |

No `models.py` yet: the module owns no table. Persisting each call and its hits
(`retrieval_calls`, `retrieval_hits`) arrives with experiment executions.

## A query, step by step

1. The build must be `ready`; a half-built index would answer by when it was asked.
2. The query is embedded with the **build's** embedding profile, never one chosen by the
   caller: vectors of different models are not comparable. Dense search, the only
   strategy a profile can have today, compares vectors, which is why the query is
   embedded at all.
3. The vector store returns `top_k` neighbours of the collection `external_index_ref`;
   `score_threshold` drops the weaker ones. The whole collection is searched: it holds the
   chunks of the build's snapshot, which is the search space, so nothing in the profile
   narrows it. The readers can still restrict a query to some `document_id`s; no caller
   uses it today.
4. Each hit is enriched from Postgres with chunk, document, filename, ordinal, page and
   text. A vector whose chunk no longer exists keeps its place with `chunk_id = null` and
   the text the vector store holds.

The response carries `timings` (embed, search, read back, total) so the cost of embedding
the query can be measured before anything is optimised, and `corpus_id` plus
`chunking_configuration_id` so a client can open each hit in the chunk viewer.

## Scores

Higher is better on every store and space. Cosine and inner product are reported as
similarities; a Euclidean distance `d` becomes `1 / (1 + d)`. Chroma reports `1 - cosine`,
`1 - dot` and the *squared* Euclidean distance, Qdrant reports cosine and dot as
similarities and Euclid as a distance: `distances.py` turns both into the same number, and
`temporal/tests/test_vector_store_readers.py` writes and reads back each space on each
store to keep it so.

## Dependencies

Depends on `indexes` (the build), `pipelines` (retrieval, embedding and vector store
profiles), `artifacts` and `documents` (enrichment), `corpora` (snapshot documents) and
`components` (contracts and keys). The worker imports `embedders.py`, `distances.py` and
`readers/`; nothing here imports the worker.
