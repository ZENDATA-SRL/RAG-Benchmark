# RAG Bench UI

Browser client for the benchmark flow: create a corpus, upload PDFs, compose a
chunking configuration from the component registry, materialise, and inspect chunks
on the native PDF; then freeze a snapshot of the corpus and build an index over it.

## Indexing

- **Corpus page → Freeze snapshot**: every stored document, or the selected ones. The
  corpus page lists its snapshots, each with a *Build index* shortcut.
- **Indexes page** (`/indexes`): embedding and vector store profiles (forms generated from
  the registry schema, like the configuration wizard), index builds with their status
  (polled while one is running), a *Start/Restart* action and a detail view with the chunk
  count and the vector store collection.

`SchemaForm` drops the schemas' `$schema` (draft 2020-12, unknown to the ajv8 validator)
and hides rjsf's "add property" control for schemas that allow extra keys.

## Stack

React, TypeScript, Vite, Tailwind, TanStack Query, React Router, `@rjsf/core`.
API types are generated from OpenAPI — do not edit `src/api/schema.d.ts` by hand.

## Commands

```bash
cp .env.example .env          # optional; defaults proxy to http://localhost:8000
npm install
npm run generate:api          # refresh openapi.json + schema.d.ts from the FastAPI app
npm run dev
npm run typecheck
npm run test
npm run lint
```

The Vite dev server proxies `/api` and `/health` to `API_PROXY_TARGET`. The only
browser-facing variable is `VITE_API_BASE_URL` (empty = same origin).

Playwright (`npm run test:e2e`) walks the empty-state path and skips if the API
is not on `:8000`. Install the browser once with `npx playwright install chromium`.

## Docker

```bash
docker compose up frontend
```

The container serves the same dev server and proxies to the API on the host
(`host.docker.internal:8000`).
