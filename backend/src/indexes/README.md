# indexes

Index builds: the population of a vector store from a frozen set of documents. An index
build is the unit an experiment chooses, already built, instead of rebuilding anything at
launch.

## Entity (`models.py`)

| Entity | Identity |
|---|---|
| `IndexBuild` | `chain_fingerprint` over corpus snapshot + chunking configuration + embedding profile + vector store profile |

The snapshot is part of the identity because the search space is a property of the index.
Repeating the same choice of snapshot and profiles returns the existing build.

The chunks of a build are not stored as a set: they are the chunks of the build's chunking
configuration for the documents in its snapshot. `IndexBuildRepository.list_chunks` and
`count_chunks` express that join, and are what the worker reads to embed.

## Services (`service.py`)

- `IndexBuildService` — `get`, `get_with_chunk_count`, `list` (optionally by snapshot), and
  `get_or_create_reporting` (the build plus whether this call created it) after checking
  that the snapshot and every profile exist.
- `IndexCorpusService` — `start` launches `IndexCorpusWorkflow` with a workflow id derived
  from the build id; a second identical request reports the running workflow.

## Routes (`router.py`)

| Route | Purpose |
|---|---|
| `POST /index-builds` | Create, idempotent by `chain_fingerprint`; answers `created` |
| `POST /index-builds/{id}/start` | Start indexing, `202`; `started=false` if the same work is already running |
| `GET /index-builds` | Paginated, newest first; `?corpus_snapshot_id=` keeps the builds over one search space |
| `GET /index-builds/{id}` | The build with its status and `chunk_count` (the chunks available now, so it grows while chunks are materialised) |

A build is created from a snapshot (`POST /corpora/{id}/snapshots`), a chunking
configuration, an embedding profile and a vector store profile, all reachable over HTTP.

## What the worker does with it

`IndexCorpusWorkflow` materialises the chunks of the snapshot, embeds them in batches to
object storage and upserts each batch into the vector store collection named after
`external_index_ref` (vector id = chunk id, metadata `index_build_id`, `document_id`,
`ordinal`). A build ends `ready` once every vector is in the store, `failed` if a document
could not be chunked or an activity failed for good. Details in `temporal/README.md`.

## Dependencies

Depends on `pipelines` (configuration and profiles), `artifacts` (chunks) and `corpora`
(snapshots).
