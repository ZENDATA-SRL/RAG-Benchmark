# RAG Bench UI

Browser client for the Milestone 1 flow: create a corpus, upload PDFs, compose a
chunking configuration from the component registry, materialise, and inspect chunks
on the native PDF.

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
