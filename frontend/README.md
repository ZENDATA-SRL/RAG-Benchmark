# RAG Bench UI

Browser client for the benchmark flow: create a corpus, upload PDFs, compose a
chunking configuration from the component registry, materialise, and inspect chunks
on the native PDF; then freeze a snapshot of the corpus, build an index over it and try
queries against it.

## Pages

| Route | Page |
|---|---|
| `/corpora`, `/corpora/:corpusId` | Corpora list; corpus detail with upload, documents, snapshots, preview and materialisation |
| `/corpora/:corpusId/documents/:documentId/chunks` | Chunk viewer on the native PDF, with the parse text; `?configuration=` picks the configuration and `?chunk=` opens on one chunk |
| `/configurations`, `/configurations/new` | Chunking configurations with their coverage; the wizard that composes one |
| `/indexes` | Embedding and vector store profiles, index builds, and the query panel of a ready build |
| `/qa-sets`, `/qa-sets/:qaSetId` | QA sets; questions with their gold documents, CSV/JSONL import with its summary, freeze |
| `/experiments`, `/experiments/:experimentId` | Experiments and the wizard that creates one; variants, runs and the *Launch run* action |
| `/experiments/:experimentId/runs/:runId` | A run: polled progress with cancel and resume, results per variant, questions and their drill-down |
| `/components` | The component registry |

## Indexing

- **Corpus page → Freeze snapshot**: every stored document, or the selected ones. The
  corpus page lists its snapshots, each with a *Build index* shortcut.
- **Indexes page** (`/indexes`): embedding and vector store profiles (forms generated from
  the registry schema, like the configuration wizard), index builds with their status
  (polled while one is running), a *Start/Restart* action and a detail view with the chunk
  count and the vector store collection.

## Trying queries

On the indexes page a `ready` build has a *Try query* action (`features/retrieval/`). The
panel picks or creates a retrieval profile — search strategy (every value of the enum;
only dense is accepted by the API today), top-k and score threshold from a generated form — sends the query to `POST /api/v1/retrieve` and
lists the hits with rank, score, file, page and the start of the text, plus where the time
went. Each hit links to the chunk viewer of its document, under the build's chunking
configuration and opened on that chunk; a hit whose chunk no longer exists is shown but not
linked.

`SchemaForm` drops the schemas' `$schema` (draft 2020-12, unknown to the ajv8 validator)
and hides rjsf's "add property" control for schemas that allow extra keys.

## Experiments

- **QA sets** (`features/qa-sets/`): create a set, import questions from CSV (columns
  `question`, optional `answer`, `gold_files` separated by `|`, `tags` separated by `|`,
  `answerable`) or JSONL. The questions table shows the expected answer next to each question.
  The import summary counts imported, already present, unresolved, ambiguous and invalid rows
  and lists every row that was left out with its reason. *Freeze* creates the snapshot an
  experiment uses; if the questions did not change, the existing snapshot is shown with the
  server's message.
- **Experiment wizard** (`features/experiments/`): corpus snapshot, QA set snapshot, then
  variants. Only `ready` index builds of the chosen corpus snapshot are offered, each crossed
  with the chosen retrieval profiles; one variant can be the baseline. The coverage check runs
  as soon as both snapshots are chosen: if some questions have gold documents outside the
  corpus snapshot they are listed, and *Create* stays disabled until they are explicitly
  excluded from the metrics. `variants_outside_snapshot` and `gold_coverage_choice_required`
  are shown inline.
- **Run page**: progress is polled while the run is active (cancel while running, resume
  when something is left); results have one row per variant with the baseline highlighted,
  the cutoff (1/3/5/10) and an optional tag slice. Every value is shown as
  `mean (effective/asked)`, so excluded questions are never hidden, together with the corpus and
  QA set snapshot the numbers were computed on. A CSV download and the questions table are
  below; clicking a question opens the hits of every variant side by side, with a badge on
  hits from a gold document.

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

Playwright (`npm run test:e2e`) walks the empty-state path and opens the QA set and experiment pages, and skips if the API
is not on `:8000`. Install the browser once with `npx playwright install chromium`.

## Docker

```bash
docker compose up frontend
```

The container serves the same dev server and proxies to the API on the host
(`host.docker.internal:8000`).
