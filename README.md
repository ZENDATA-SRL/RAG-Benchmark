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
docker compose up -d --wait   # minio (+ bucket), temporal, temporal-ui, worker
uv run alembic -c backend/alembic.ini upgrade head
cd backend && uv run uvicorn src.main:app --reload
cd frontend && npm install && npm run dev   # http://localhost:5173
```

With the API and the worker up, one script exercises the whole backend over HTTP — corpus,
upload, profiles, configuration, preview, materialisation, polling, chunk and parse
inspection — and exits non-zero at the first deviation:

```bash
uv run python scripts/mvp_smoke.py
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

The UI answers on `http://localhost:5173` (`docker compose up frontend` if you prefer the
container). The API answers on `http://localhost:8000`:

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness probe |
| `GET /api/v1/components` | Registered components with their JSON Schema; feeds the dynamic forms of the UI |
| `GET /docs` | OpenAPI documentation |

Other consoles: MinIO on [`localhost:9001`](http://localhost:9001), Temporal on
[`localhost:8080`](http://localhost:8080).

## Configuration

`.env` is the **single source of truth**: `docker-compose.yml` provisions the containers
from it and the application reads it through `Settings`, so the credentials cannot drift
apart. Copy it from `.env.example`, which documents every variable and contains no real
secret. Credentials never live in the database (RT-S01).

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
    sources/          connections and imports
  tests/
frontend/             React + Vite UI: corpus, upload, configuration, chunks
scripts/              mvp_smoke.py, the end-to-end check of the backend flow
temporal/             worker, workflows, activities and builtin implementations
  components/         parser, chunker and embedder code, invoked only by the worker
  tests/
```

Module conventions and dependency direction are in
[`.claude/skills/backend-structure/SKILL.md`](.claude/skills/backend-structure/SKILL.md): `router → service → repository → models`.

### Where the builtin components live

Split in two on purpose, and the direction matters:

- **`backend/src/components/builtin/`** — the `Parser`/`Chunker` protocols, `ParseOutput`,
  `ChunkPayload`, and one descriptor per component (key, version, `params_schema`,
  `capabilities`). Declarative only. The API seeds the registry and renders the UI forms from
  these without importing any parsing library.
- **`temporal/components/`** — the implementations and the `BUILTIN_PARSERS` /
  `BUILTIN_CHUNKERS` maps (embedders are resolved in `components/embedders/shared.py`) that resolve a key to running code. Only the worker executes them.

Dependencies flow `temporal → backend`, never the reverse. The API can tell that a component
key was *declared*; only the worker can tell it is *runnable*, so it calls
`assert_registry_complete()` at startup and fails there if a descriptor has no implementation.
