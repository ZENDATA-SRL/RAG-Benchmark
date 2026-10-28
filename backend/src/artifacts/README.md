# artifacts

What parsing and chunking produced, **per document**: the cached artefacts, the claim and
completion protocol the worker uses to write them, and the read side that lets a user
inspect them.

## Entities (`models.py`)

| Entity | Identity |
|---|---|
| `ParsingResult` | `cache_key` = document content hash + parsing profile hash; the output JSON is on object storage (`output_uri`) |
| `ChunkResult` | `cache_key` = document content hash + chunking configuration hash |
| `Chunk` | `(chunk_result_id, ordinal)`; text, modality and metadata are rows, vectors are not |

Status is `pending → running → ready | failed` (`ArtifactStatus`). The state of parsing and
chunking belongs to the artefact, never to the document: a document can be ready under one
configuration and missing under another.

Two composite foreign keys on `chunk_results` guarantee in the database that a chunk result
is built from a parse of the parsing profile its configuration declares.

## Services (`service.py`)

- `ArtefactService` — used by the worker's activities. `claim_parsing_result` and
  `claim_chunk_result` return the cached artefact when it is `ready`, or insert a `pending`
  row: the unique `cache_key` is the lock between concurrent workers. `complete_*` and
  `fail_artefact` close the artefact; `documents_needing_chunking` returns only the
  documents without a `ready` chunk result, which is why adding documents to a corpus only
  chunks the new ones.
- `CoverageService` — for a configuration and a corpus, how many documents are `ready`,
  `failed` and `missing`. The three counts always sum to the corpus size.
- `InspectionService` — chunks of a document under a configuration (paginated, in ordinal
  order), a single chunk, the chunk result state, and the per-page text of a parse read back
  from object storage.

## Routes (`router.py`)

| Route | Purpose |
|---|---|
| `GET /chunking-configurations/{id}/coverage?corpus_id=` | Is this configuration materialised on this corpus, and how far |
| `GET /documents/{id}/chunks?chunking_configuration_id=` | Chunks of a document, with the state of their chunk result |
| `GET /documents/{id}/chunks/compare?configurations=a,b` | The same document under several configurations, side by side |
| `GET /chunk-results?document_id=&chunking_configuration_id=` | State of one chunking artefact |
| `GET /chunks/search?chunking_configuration_id=&q=[&corpus_id=]` | Chunks of a configuration containing some words in sequence, whatever whitespace separates them (parsers break lines and pad words differently); paged |
| `GET /chunks/{id}` | One chunk |
| `GET /documents/{id}/parse?parsing_profile_id=` | Per-page parse text, to tell a bad parse from a bad chunking |

A pair that was never materialised is a `404` (`ChunkResultNotFoundError`), not an empty
list: "never chunked" and "chunked into zero chunks" are different answers.

## Dependencies

Depends on `pipelines` (configurations and profiles), `documents` and `corpora`.
`materializations` and `indexes` read the artefacts through this module.
