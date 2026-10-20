# pipelines

The configuration side of the pipeline: reusable profiles and the chunking configurations
built from them. Nothing here is executed or materialised; the modules that do the work
(`artifacts`, `materializations`, `indexes`) all point back at these rows.

## Entities (`models.py`)

| Entity | Identity |
|---|---|
| `ParsingProfile`, `ChunkingProfile`, `EmbeddingProfile`, `VectorStoreProfile`, `RetrievalProfile` | `config_hash` = component version + canonical params |
| `ChunkingConfiguration` | Parsing profile + chunking profile; the unit of comparability of chunk-level gold |

The profile name is excluded from every hash: two profiles that behave the same are one
row, whatever the user called them.

## Services (`service.py`)

- `ProfileService` — get-or-create for the five profile types. Params (`index_params` for
  vector stores) are validated against the component version's `params_schema`; chunkers
  must declare `capabilities.scope = document`.
- `ChunkingConfigurationService` — get-or-create of a configuration from two profile ids,
  `expand` (configuration + its two profiles, so the UI labels a row in one call) and
  `compose` (both profiles and the configuration in one transaction, for a single UI form).

## Routes (`router.py`)

| Route | Purpose |
|---|---|
| `POST/GET /parsing-profiles`, `GET …/{id}` | Parsing profiles |
| `POST/GET /chunking-profiles`, `GET …/{id}` | Chunking profiles |
| `POST/GET /embedding-profiles`, `GET …/{id}` | Embedding profiles. `dimensions`, when set, is checked against the vectors the worker gets back |
| `POST/GET /vector-store-profiles`, `GET …/{id}` | Vector store profiles; for `chromadb`, `index_params` holds the HNSW configuration of the collection |
| `POST/GET /chunking-configurations`, `GET …/{id}` | Configurations, with profiles inlined |
| `POST /chunking-configurations/compose` | Both profiles and the configuration in one call |

Every create endpoint is idempotent and answers `created: true|false`; when a row is reused,
`detail` carries `REUSED_DETAIL` from `constants.py`, which `indexes` uses too.

`GET /chunking-configurations/{id}/coverage` shares the URL prefix but lives in `artifacts`,
because it is computed from the per-document chunk results.

## Dependencies

`pipelines` depends only on `components`. It is the base of the other pipeline modules:

```
pipelines ← artifacts ← materializations
          ↖ indexes
```

`exceptions.py`: `ProfileNotFoundError` (also used by the other modules for any missing
referenced row), `UnsupportedChunkerScopeError`, `ChunkingConfigurationNotFoundError`.
