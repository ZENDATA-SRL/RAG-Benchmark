# RAG Benchmark

Platform for building, materialising and comparing RAG pipelines in a reproducible way:
the same corpus, the same parsing and chunking configuration and the same index always
produce the same artefacts, because every entity is addressed by the hash of what it is
made of.

- Requirements: [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md)
- Data model: [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md)
- Sprint plan: [`sprint/README.md`](sprint/README.md)
- Backend modules: [`backend/README.md`](backend/README.md)
- Temporal worker, workflows and activities: [`temporal/README.md`](temporal/README.md)
- Each module has its own README: `backend/src/<module>/README.md`, `temporal/{activities,workflows,components}/README.md`

## Requirements

- Docker with Compose v2
- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Node.js 22+ (for the UI)

## Startup

```bash
cp .env.example .env          # adjust if a port is already taken
uv sync
docker compose up -d --wait   # minio (+ bucket), temporal, temporal-ui, chromadb, qdrant, frontend
uv run alembic -c backend/alembic.ini upgrade head
cd backend && uv run uvicorn src.main:app --reload
PYTHONPATH=.:backend uv run python -m temporal.worker   # from the repository root, own terminal
```

The UI is served on <http://localhost:5173> by the `frontend` Compose service. To run it from
a local checkout instead, stop that service and use
`cd frontend && npm install && npm run dev`.

`postgres` and `worker` are opt-in Compose profiles. The worker (it parses, chunks, embeds,
indexes and runs the experiments; without it materialisations, index builds and runs stay pending) can run from the
checkout as above or as a container, which reads AWS credentials for Bedrock from `~/.aws`
(see the Temporal README):

```bash
docker compose --profile worker up -d --build worker
```

The API answers retrieval queries itself (`POST /api/v1/retrieve`), so besides the worker it
also embeds text and reaches the vector stores: it needs the credentials of the embedders you
use and the `CHROMA_*` / `QDRANT_*` addresses in `.env`. For OpenAI, export `OPENAI_API_KEY`
in the shell that starts the API and the worker: the library reads the process environment,
which `.env` does not populate. For Bedrock, the host's `~/.aws` profile (or the `AWS_*`
variables) is picked up directly by the API run from the host.

With the API and the worker up, one script exercises the whole backend over HTTP — corpus,
upload, profiles, configuration, preview, materialisation, polling, chunk and parse
inspection — and exits non-zero at the first deviation. With `--embedder` it also freezes a
snapshot, builds an index and queries it; that part calls the real embedding model, so its
credentials must be available to both the worker and the API:

```bash
uv run python scripts/mvp_smoke.py
uv run python scripts/mvp_smoke.py --embedder openai --vector-store qdrant
```

The interactive API documentation is on <http://localhost:8000/docs>.

### PostgreSQL

The stack assumes a **PostgreSQL 13+ already listening on `localhost:5432`** with the
credentials in `.env`, which is the usual case on a development machine. Create the two
databases once:

```bash
createdb -U postgres rag-bench
createdb -U postgres rag-bench-test
```

If you have no local PostgreSQL, Compose ships one behind an opt-in profile:

```bash
docker compose --profile postgres up -d --wait
```

Should port 5432 already be busy, publish the container elsewhere and align `DATABASE_URL`:

```bash
POSTGRES_PORT=5433 docker compose --profile postgres up -d --wait
# then, in .env: DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5433/rag-bench
```

The API answers on `http://localhost:8000`:

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness probe |
| `GET /api/v1/components` | Registered components with their JSON Schema; feeds the dynamic forms of the UI |
| `POST /api/v1/retrieve` | Query a ready index build under a retrieval profile; the retrieval tool |
| `GET /docs` | OpenAPI documentation |

Other consoles and services: MinIO on [`localhost:9001`](http://localhost:9001), Temporal on
[`localhost:8080`](http://localhost:8080), ChromaDB on `localhost:8001`, Qdrant on
[`localhost:6333`](http://localhost:6333/dashboard).

## Configuration

`.env` is the **single source of truth**: `docker-compose.yml` provisions the containers
from it and the application reads it through `Settings`, so the credentials cannot drift
apart. Copy it from `.env.example`, which documents every variable (database, object
storage, Temporal, ChromaDB, Qdrant, AWS profile for the worker, embedder credentials,
upload limits, CORS) and
contains no real secret. The aim is that credentials never live in the database;
the one known exception, embedder keys typed into profile params, is listed in the Temporal
README.

## Tests

```bash
# create the test database once
createdb -U postgres rag-bench-test
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/rag-bench-test \
  uv run alembic -c backend/alembic.ini upgrade head

uv run pytest                      # everything
uv run pytest -m "not integration" # unit only: no Postgres, no MinIO
```

Tests marked `integration` need the Compose services; the others run anywhere.

## Structure

```
backend/
  alembic/            migrations; `alembic.ini` is invoked from the repository root
  src/
    main.py           app creation, router registration, error handler
    settings.py       configuration read from the environment
    core/             hashing, get-or-create, domain errors, logging
    infrastructure/   database (base, session, enums), object storage, temporal client
    components/       registry of pluggable components: contracts + descriptors (parser, chunker, embedder, vector store)
    corpora/          corpora and snapshots
    documents/        documents
    pipelines/        profiles and chunking configurations
    artifacts/        per-document parse and chunk results, coverage, inspection
    materializations/ chunk materialisation runs and their progress
    indexes/          index builds over a corpus snapshot
    retrieval/        dense search over a ready index build, embedders, vector store readers
    qa_sets/          question sets, authoring, gold documents and evidence chunks, import/export, snapshots
    experiments/      retrieval experiments: variants, runs, document- and chunk-level metrics, results by chunking configuration
    sources/          connections and imports
    dependencies.py   FastAPI dependencies (object storage, workflow client)
  tests/
frontend/             React + Vite UI: corpora, upload, snapshots, configurations, chunks, indexes, question sets and annotation, experiments, components
scripts/              mvp_smoke.py, the end-to-end check of the backend flow (and, opt-in, of retrieval, of a retrieval experiment and of its re-evaluation on confirmed evidence)
temporal/             worker, workflows, activities and builtin implementations
  activities/         parsing, chunking, materialisation, indexing, embedding, vector store writes, experiment runs
  workflows/          ProcessDocument, MaterializeChunks, IndexCorpus, RunExperiment, RunVariant
  components/         parser, chunker and vector store write code, invoked only by the worker
  tests/
docs/                 requirements and data model
sprint/               sprint plan (in Italian)
docker-compose.yml    postgres (opt-in), minio, temporal, chromadb, qdrant, worker (opt-in), frontend
Dockerfile.worker     image of the Temporal worker
```

Module conventions and dependency direction are in
[`.claude/skills/backend-structure/SKILL.md`](.claude/skills/backend-structure/SKILL.md): `router → service → repository → models`.

### Where the builtin components live

Split on purpose, and the direction matters:

- **`backend/src/components/builtin/`** — the `Parser`/`Chunker`/`VectorStoreReader`
  protocols, `ParseOutput`, `ChunkPayload`, `VectorHit`, and one descriptor per component
  (key, version, `params_schema`, `capabilities`). Declarative only. The API seeds the
  registry and renders the UI forms from these without importing any parsing library.
- **`backend/src/retrieval/`** — the code both processes run: the embedders
  (`BUILTIN_EMBEDDERS`), the vector store readers (`BUILTIN_VECTOR_STORE_READERS`) and the
  shared distance mapping. Retrieval is synchronous and called many times per question, so it
  runs in the API rather than through a workflow; the worker imports the same embedders, so a
  query is embedded by exactly the code that embedded its index.
- **`temporal/components/`** — parsers, chunkers and the vector store writers, with the
  `BUILTIN_PARSERS` / `BUILTIN_CHUNKERS` / `BUILTIN_VECTOR_STORES` maps that resolve a key to
  running code. Only the worker executes them.

Dependencies flow `temporal → backend`, never the reverse. The API can tell that a component
key was *declared*; only the worker can tell it is *runnable*, so the worker calls
`assert_registry_complete()` at startup and fails there if a descriptor has no
implementation, or a vector store has no reader.
