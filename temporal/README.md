# Temporal worker

Durable execution of everything that cannot run inside an HTTP request: parsing a 300-page
PDF, chunking a corpus, building an index. Workflows and activities land in Sprint 3; today
this package holds the **builtin component implementations**.

## Why the implementations are here and not in the backend

The worker is the only process that ever invokes a parser or a chunker. Keeping the code here
means the API image does not carry `pypdf` or `langchain-text-splitters`, and a change to an
extraction heuristic redeploys the worker alone.

What stays in the backend is the *declaration*:

| In `backend/src/components/builtin/` | In `temporal/components/` |
|---|---|
| `Parser` / `Chunker` protocols | classes implementing them |
| `ParseOutput`, `ChunkPayload` | — |
| descriptors: key, version, `params_schema`, `capabilities` | `BUILTIN_PARSERS`, `BUILTIN_CHUNKERS` |

The API must serve `params_schema` to render the UI forms (RT-U01) with no worker running, so
the schemas cannot live only here. Dependencies therefore flow **`temporal → backend`**; the
reverse would be a cycle, since the worker already imports `ArtefactService`, the object
storage and the session factory.

## The split's one risk, and its guard

Because the API declares components without importing their code, nothing at import time
notices a descriptor whose implementation was never written. Two checks close that gap:

- `assert_registry_complete()` runs at worker startup and fails loudly on a declared-but-
  unimplemented component. Boot time is the right place: an activity would discover it hours
  into a run.
- `tests/test_component_registry.py` asserts the correspondence in **both** directions and
  that each implementation satisfies its protocol.

## Layout

```
temporal/
  client.py         connect to the Temporal frontend with the shared data converter
  codec.py          SizeGuardCodec: rejects payloads over 128 KB (RT-O02)
  config.py         worker session factory, per-activity transaction, data converter
  task_queues.py    ingestion / parsing / chunking queues (RT-O03)
  worker.py         registers activities + workflows, asserts the registry at startup
  workflow_ids.py   deterministic workflow ids (RT-O01)
  activities/       parse_document, chunk_document, run reads, materialisation progress
  workflows/        ProcessDocumentWorkflow, MaterializeChunksWorkflow
  components/
    __init__.py       BUILTIN_PARSERS / BUILTIN_CHUNKERS, resolve_*, assert_registry_complete
    parsers/          pypdf
    chunkers/         recursive, markdown
  tests/
```

See [`sprint/SPRINT-03-temporal-parsing-chunking.md`](../sprint/SPRINT-03-temporal-parsing-chunking.md).

## Running outside Docker

Neither `temporal` nor `src` is an installed package: both source roots have to be on
`PYTHONPATH`, since here there is no `pythonpath` (pytest) nor `prepend_sys_path` (alembic) to
supply them. From the repository root:

```bash
PYTHONPATH=.:backend uv run python -m temporal.worker
```

## Tests

Run from the repository root, since `pythonpath` covers both source roots:

```bash
uv run pytest temporal/tests
```
