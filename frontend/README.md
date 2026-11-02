# RAG Bench UI

Browser client for the benchmark flow: create a corpus, upload PDFs, compose a
chunking configuration from the component registry, materialise, and inspect chunks
on the native PDF; then freeze a snapshot of the corpus, build an index over it and try
queries against it; then compare retrievers, or answer systems, in experiments.

## Pages

| Route | Page |
|---|---|
| `/corpora`, `/corpora/:corpusId` | Corpora list; corpus detail with upload, documents, snapshots, preview and materialisation |
| `/corpora/:corpusId/documents/:documentId/chunks` | Chunk viewer on the native PDF, with the parse text, sized to the window so the PDF and the chunk list scroll in their own panes; `?configuration=` picks the configuration and `?chunk=` opens on one chunk |
| `/configurations`, `/configurations/new` | Chunking configurations with their coverage; the wizard that composes one |
| `/indexes` | Embedding and vector store profiles, index builds, and the query panel of a ready build |
| `/qa-sets`, `/qa-sets/:qaSetId` | QA sets grouped by origin corpus (a new set takes the corpus name until renamed); the origin corpus of a set, its questions with their gold documents, new/edit/replace/delete of a question (gold documents picked from the origin corpus, with a filename filter), CSV/JSONL import with its summary, export, freeze; `?configuration=` shows the evidence status of each question under a chunking configuration, with a filter and the counts, *Suggest chunks* and the set's suggestion jobs |
| `/qa-sets/:qaSetId/questions/:questionId/annotate` | Annotation of one question under the chunking configuration in `?configuration=`: the chunk viewer on a gold (★) or corpus document (`?document=`), chunks marked sufficient or supporting, and the evidence panel to save a draft, confirm, or record not found; *Next to review* goes on to the next question waiting. With `?transfer=` it is the review queue of a suggestion job |
| `/transfers/:transferId` | A suggestion job: ranking progress, reviewed and confirmed counts, recall ceiling, its weights and thresholds, the questions by state, *Start review* |
| `/answer-profiles` | Answer profiles: name, start of the system prompt, the profile each was derived from; *New answer profile*, *Derive*, and a detail with the parameters and what changed from the parent |
| `/experiments`, `/experiments/:experimentId` | Experiments grouped by corpus and then by QA set, with their type and the snapshots each one uses, and the wizard that creates one; an experiment's type, corpus and QA set, variants (with the answer profile for Q&A), runs and the *Launch run* action |
| `/experiments/compare` | Comparison of every variant run on one QA set snapshot (see below) |
| `/experiments/:experimentId/runs/:runId` | A run: polled progress with cancel and resume, results grouped by chunking configuration, re-evaluation, questions and their drill-down |
| `/components` | The component registry, one collapsible section per pipeline stage (source → judge) with its icon, component count and availability; each version expands to its parameters (name, type, default) |

Every table sits in a frame bounded to the window (`TableFrame`): long lists scroll inside it
with the column names kept visible, instead of stretching the page.

## Indexing

- **Corpus page → Freeze snapshot**: every stored document, or the selected ones. The
  corpus page lists its snapshots, each with a *Build index* shortcut.
- **Indexes page** (`/indexes`): embedding and vector store profiles (forms generated from
  the registry schema, like the configuration wizard; no name field, since the server names
  profiles, configurations, index builds and variants after what they are), index builds with their status
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

`SchemaForm` drops the schemas' `$schema` (draft 2020-12, unknown to the ajv8 validator),
hides rjsf's "add property" control for schemas that allow extra keys, and edits string
parameters whose key ends in `prompt` in a multi-line text area.

## Experiments

- **QA sets** (`features/qa-sets/`): create a set, import questions from CSV (columns
  `question`, optional `answer`, `gold_files` separated by `|`, `tags` separated by `|`,
  `answerable`) or JSONL, or write them one by one (`QuestionEditor`). A question a snapshot
  holds is marked *frozen*: it cannot be edited or deleted, and saving it *replaces* it with a
  new question. *Export* downloads the set, or a snapshot, as CSV or JSONL in the import
  format. The questions table shows the expected answer next to each question.
- **Annotation** (`AnnotationPage`, `EvidencePanel`, `evidence.ts`): pick a chunking
  configuration on the set page, then *Annotate* a question. Chunks are marked with the
  *sufficient* / *supporting* toggles on each row, or with the keys `s`, `p`, `x` on the
  selected chunk; the panel lists the picked chunks across documents, and its buttons explain
  why they are disabled (no chunk to confirm, chunks on a not-found, no annotator name). The
  annotator's name is remembered in the browser. The chunk rows come from the same
  `ChunkNavigator` the chunk viewer uses, through its `renderChunkActions` prop.
- **Suggested chunks** (`features/transfers/`): *Suggest chunks* on the set page starts a job
  under the chosen configuration, from the question and its answer or from the evidence
  confirmed in another configuration, with the embedder and, folded away, the weights and
  thresholds; questions whose documents have no chunks there are listed and can be left
  out. The job page polls the ranking and lists the questions by state. *Start review* opens
  the annotation page in queue mode: a *Candidates* tab lists every chunk of the gold
  documents best first, with band, combined and per-signal scores and the grade toggles
  (texts flowed onto one line, as some extractions break after every word); pre-selected
  candidates come ticked but unsaved; *Document* shows the chunk viewer with each
  candidate's rank and score; *Search* finds chunks by their words when nothing is plausible.
  With a source, the chunks confirmed there are shown above. Keys: `j`/`k` or `↑`/`↓` move,
  `s`/`p`/`x` grade, `Enter` confirms and goes to the next question waiting, `n` records not
  found and goes on; at the end of the queue the job page opens again.
  The import summary counts imported, already present, unresolved, ambiguous and invalid rows
  and lists every row that was left out with its reason. *Freeze* creates the snapshot an
  experiment uses; if the questions did not change, the existing snapshot is shown with the
  server's message.
- **Answer profiles** (`features/answer-profiles/`): the form is generated from the schema of
  an `answer_system` component (provider, model, system prompt, temperature, ...). *Derive
  from* copies another profile's parameters and records it as the parent, so the detail lists
  what changed; the server names the profile and returns the existing one for the same
  parameters. An answer system the worker marked unavailable (no model credentials) is shown
  with its reason and cannot be used. Emptied text fields are dropped before sending, so they
  hash like fields left out.
- **Experiment wizard** (`features/experiments/`): the type (*Retrieval* or *Q&A*), corpus
  snapshot, QA set snapshot, then variants. Only `ready` index builds of the chosen corpus snapshot are offered, each crossed
  with the chosen retrieval profiles and listed by index build and retrieval profile until
  the server names them; one variant can be the baseline. A Q&A experiment adds the answer
  profiles as a third dimension of the cross (profiles of an unavailable system are offered
  struck through, with the reason on hover) and the scope of its set metrics: every chunk
  retrieved, or the chunks the answer cites, which needs systems that declare citations. When
  the variants differ by the answer profile and by the index or the retrieval profile at
  once, the wizard says the effects cannot be told apart (informative only).
  `answer_profile_required`, `citations_not_supported` and `answer_system_not_available` are
  shown inline. The coverage check runs
  as soon as both snapshots are chosen: if some questions have gold documents outside the
  corpus snapshot they are listed, and *Create* stays disabled until they are explicitly
  excluded from the metrics. `variants_outside_snapshot` and `gold_coverage_choice_required`
  are shown inline. Once index builds are chosen, the chunk-level evidence of each of their
  configurations is shown (confirmed, not found, still to review): informative only, since
  chunk metrics count the confirmed questions and exclude the rest with their reason.
- **Run page**: progress is polled while the run is active (cancel while running, resume
  when something is left). Results are grouped by the chunking configuration the variants
  search: each group states its parser and chunker, how far its evidence was reviewed and the
  recall ceiling, and its rows have one row per variant with the baseline highlighted, the
  document-level and the chunk-level columns, the cutoff (1/3/5/10) and an optional tag slice.
  Every value is shown as `mean (effective/asked)`, with the excluded questions per reason on
  hover, so excluded questions are never hidden, together with the corpus and QA set snapshot
  the numbers were computed on. Selecting variants and *Compare selected* shows only those;
  every column stays whichever groups they come from. A Q&A run adds two sections after the ranked columns (which are then those of each
  execution's first call): *Set*, with the set recall next to the set size and the share of
  repeated hits, and *Calls*; a retrieval run shows neither. *Re-evaluate* scores the run
  again on the worker on the evidence as it is now, with a progress bar while it runs and the
  results reloaded when it ends; the date and fingerprint of the evidence used are shown
  above the table. A CSV download and the questions table (document and chunk outcome per
  variant) are below; clicking a question opens the chunks of every variant side by side,
  with badges on chunks from a gold document, on evidence chunks and on cited ones, the
  evidence status of each variant's configuration, and the evidence chunks it did not
  retrieve, each linking to the annotation page. An execution that searched more than once
  lists its calls (query, hits, chunks new to that call), a chunk returned by several calls
  shows each call and rank (`×2 · call 1 rank 1, call 2 rank 2`), and chunks cited without
  being retrieved come last. In a Q&A run the questions table shows, under each question, its expected answer (or that
  it is not answerable) and, for each variant, the start of its answer (whole on hover),
  whether it refused and whether that was right, then the retrieval outcome; *Download
  answers* gets every answer of the run as CSV, one row per question, variant and
  repetition. A Q&A run also adds an *Answer* section to the results:
  `refusal_accuracy`, latency p50 and p95, model latency p50, tokens in and out, each with
  its sample. Its drill-down shows the question's expected answer and, for each execution,
  the answer, whether it refused and whether that was right, the model, the tokens and where
  the time went, with a link to the execution's trace on Langfuse when the run was traced. Every results column explains itself: hovering its name shows what the
  metric measures, and the *How to read these metrics* section under the table lists each
  column on screen with that description, whether higher or lower is better and the statistic
  the cell reports (mean, median or p95). The wording is served by the API with each metric.
- **Comparison page** (`/experiments/compare`, from the *Compare variants* button of the
  experiments list): pick a QA set and one of its snapshots, then *Retrieval* or *Q&A*, which
  are never mixed. Every variant of every experiment run on that snapshot is drawn, each
  experiment with its latest finished run. A *Best on* strip counts how many metrics each
  variant leads, out of the same total for all (the metrics at least two variants have a value
  on), flagging the variants with no value on some, such as the chunk-level ones, and naming
  the metrics left out because a single variant has a value; below, every metric is a small bar chart on a shared scale (0–1 for a
  score), in sections: documents, chunks and, for Q&A, the retrieved set, the searches and
  the answers. The best bar is highlighted, a dashed line marks the baseline (the one marked
  in its experiment, or the variant chosen in *Baseline*), and each row shows the value, the
  change against the baseline (in points for a score, in % for a time or a count, with an
  arrow and green or red when it is an improvement or a regression) and the number of
  questions it rests on, flagged when it is fewer than the largest sample. The cutoff applies
  to the ranked metrics, and *Variants shown* hides variants without moving the baseline.
  Variants on different corpus snapshots are drawn together with a warning, and experiments
  without a finished run are listed as left out. The selection lives in the URL
  (`?qaSet=&snapshot=&type=`), so a view can be shared.

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
is not on `:8000`. `annotation-flow.spec.ts` writes a question, confirms one evidence chunk
and checks the counts; it needs a corpus with a materialised document and leaves an empty
"e2e annotation" QA set behind, because sets cannot be deleted. `suggestion-flow.spec.ts`
starts a suggestion job for one question, reviews it from the keyboard and checks that the
evidence is confirmed; it also needs a worker serving the transfer workflow (it calls the
embedder of the newest index on that configuration, if any) and leaves an "e2e suggestion"
set behind. Install the browser once with `npx playwright install chromium`.

## Docker

```bash
docker compose up frontend
```

The container serves the same dev server and proxies to the API on the host
(`host.docker.internal:8000`).
