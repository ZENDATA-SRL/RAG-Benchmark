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

- `IndexBuildService` — `get`, and `get_or_create_reporting` (the build plus whether this
  call created it) after checking that the snapshot and every profile exist.
- `IndexCorpusService` — `start` launches `IndexCorpusWorkflow` with a workflow id derived
  from the build id; a second identical request reports the running workflow.

## Routes (`router.py`)

| Route | Purpose |
|---|---|
| `POST /index-builds` | Create, idempotent by `chain_fingerprint`; answers `created` |
| `POST /index-builds/{id}/start` | Start indexing, `202`; `started=false` if the same work is already running |

## Current limits

- No read endpoint yet (`GET /index-builds/{id}`), and no API to create a corpus snapshot,
  which `POST /index-builds` requires.
- The workflow materialises chunks and computes embeddings; writing the vectors into the
  vector store is not implemented yet.

## Dependencies

Depends on `pipelines` (configuration and profiles), `artifacts` (chunks) and `corpora`
(snapshots).
