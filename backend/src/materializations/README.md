# materializations

A user-triggered chunk materialisation: one chunking configuration applied to a set of
documents, executed by `MaterializeChunksWorkflow` on the worker. The same entry point
serves the preview on a few files and a whole corpus; only the size of the document list
changes.

## Entity (`models.py`)

| Entity | Identity |
|---|---|
| `MaterializationRun` | `workflow_id`, deterministic from the configuration and the document set |

The row is a denormalised copy of the run for the UI: `status`, `document_count` and
`progress` (`ready`, `failed`, `cached`, `pending`, always summing to `document_count`).
The authoritative state stays in Temporal. Per-document failures are not copied here: they
are read from `chunk_results.error` in `artifacts`.

## Services (`service.py`)

- `MaterializationService` — `start` resolves the documents (explicit ids, or every
  document of a corpus), refuses any document that is not `stored`, opens the run row and
  starts the workflow. Starting the same work twice returns the existing run with
  `started=false` instead of an error. `cancel` stops the workflow and marks the run
  `failed` with reason `cancelled`.
- `MaterializationRunService` — the run row only, with no Temporal dependency: `open_run`,
  `update_progress` and `complete_run` are called by the worker's activities; `get`, `list`
  and `failures` serve the API. Following a run never needs Temporal to be reachable.

## Routes (`router.py`)

| Route | Purpose |
|---|---|
| `POST /materializations` | Start, `202`; body has `chunking_configuration_id` and either `document_ids` or `corpus_id` |
| `GET /materializations?corpus_id=&chunking_configuration_id=` | History, newest first |
| `GET /materializations/{id}` | Progress and failed documents; polled by the UI |
| `POST /materializations/{id}/cancel` | Cancel a running materialisation |

## Dependencies

Depends on `pipelines` (configuration lookup), `artifacts` (failed chunk results),
`documents` and `corpora`. Workflow names, task queue and ids come from
`infrastructure/temporal/workflow_ids.py`.
