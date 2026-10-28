# pipelines

The configuration side of the pipeline: reusable profiles and the chunking configurations
built from them. Nothing here is executed or materialised; the modules that do the work
(`artifacts`, `materializations`, `indexes`, `retrieval`) all point back at these rows.

## Entities (`models.py`)

| Entity | Identity |
|---|---|
| `ParsingProfile`, `ChunkingProfile`, `EmbeddingProfile`, `VectorStoreProfile` | `config_hash` = component version + canonical params |
| `RetrievalProfile` | `config_hash` = canonical JSON of `top_k`, `strategy`, `score_threshold`; no component version of its own |
| `ChunkingConfiguration` | Parsing profile + chunking profile; the unit of comparability of chunk-level gold |

## Names (`naming.py`)

Names are derived on creation from what a row is, never typed by the user, so a name says
what is being worked on. The name is not part of any hash.

| Entity | Name |
|---|---|
| Parsing profile | component and version: `pypdf@1` |
| Chunking profile | component, version, chunk size / overlap (schema defaults when omitted): `recursive@1 1000/200` |
| Embedding profile | component, version, `model_name`, dimensions when set: `openai@1 text-embedding-3-small 1536d` |
| Vector store profile | component, version, distance `space`: `qdrant@1 cosine` |
| Retrieval profile | strategy, `top_k`, score threshold when set: `dense top-10 ≥0.3` |
| Chunking configuration | parsing → chunking: `pypdf@1 → recursive@1 1000/200` |

When another row of the same table already reads the same (two profiles differing only in
a parameter the name does not show), the new one gets ` #` and the first six characters
of its content hash. `indexes` and `experiments` compose their names from these.

## Services (`service.py`)

- `ProfileService` — get-or-create for the five profile types. Params (`index_params` for
  vector stores) are validated against the component version's `params_schema`; chunkers
  must declare `capabilities.scope = document`. Retrieval profiles accept only what the
  retrieval engine applies today — `strategy` (`RetrievalStrategy`, only `dense` is
  executable), `top_k` and `score_threshold` — and raise
  `UnsupportedRetrievalFeatureError` (`422`) for another strategy (`constants.py` lists
  the supported ones). The reranker, MMR and fusion columns are not exposed. Query
  transformations are not part of the profile: they belong to the answer system. Nor are
  filters on document metadata: they would let two variants of an experiment search
  different documents, while the corpus snapshot is what fixes the search space.
- `ChunkingConfigurationService` — get-or-create of a configuration from two profile ids,
  `expand` (configuration + its two profiles, so the UI labels a row in one call) and
  `compose` (both profiles and the configuration in one transaction, for a single UI form).

## Routes (`router.py`)

| Route | Purpose |
|---|---|
| `POST/GET /parsing-profiles`, `GET …/{id}` | Parsing profiles |
| `POST/GET /chunking-profiles`, `GET …/{id}` | Chunking profiles |
| `POST/GET /embedding-profiles`, `GET …/{id}` | Embedding profiles. `dimensions`, when set, is checked against the vectors the worker gets back |
| `POST/GET /vector-store-profiles`, `GET …/{id}` | Vector store profiles; for `chromadb` and `qdrant`, `index_params` holds the distance space and the HNSW configuration of the collection |
| `POST/GET /retrieval-profiles`, `GET …/{id}` | Retrieval profiles: strategy, `top_k`, `score_threshold` |
| `POST/GET /chunking-configurations`, `GET …/{id}` | Configurations, with profiles inlined |
| `POST /chunking-configurations/compose` | Both profiles and the configuration in one call |

No create payload takes a name: it is derived (see above).

Every create endpoint is idempotent and answers `created: true|false`; when a row is reused,
`detail` carries `REUSED_DETAIL` from `constants.py`, which `indexes` uses too.

`GET /chunking-configurations/{id}/coverage` shares the URL prefix but lives in `artifacts`,
because it is computed from the per-document chunk results.

## Dependencies

`pipelines` depends only on `components`. It is the base of the other pipeline modules:

```
pipelines ← artifacts ← materializations
          ↖ indexes ← retrieval
```

`exceptions.py`: `ProfileNotFoundError` (also used by the other modules for any missing
referenced row), `UnsupportedChunkerScopeError`, `UnsupportedRetrievalFeatureError`,
`ChunkingConfigurationNotFoundError`.
