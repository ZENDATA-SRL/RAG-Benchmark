# infrastructure

Shared clients and persistence plumbing. Used by every domain module and by the worker.

| Package | Provides |
|---|---|
| `database/` | `Base`, `UUIDPrimaryKeyMixin`, `CreatedAtMixin`, `TimestampMixin`; the PostgreSQL enums in `enums.py` (`ArtifactStatus`, `ComponentType`, `DocumentStatus`, ...) and `TERMINAL_ARTIFACT_STATUSES`; `create_engine`, `get_session` (one session per request), `dispose_engine`. `models.py` imports every model so Alembic sees them |
| `storage/` | `ObjectStorage` protocol (`put_stream`, `put_bytes`, `get_stream`, `get_bytes`, `exists`, `build_uri`), the S3/MinIO implementation `S3ObjectStorage` built by `get_object_storage(settings)`, and the key helpers `document_key` (`documents/{content_hash}/{filename}`) and `parse_key` (`parses/{config_hash}/{content_hash}.json`) |
| `observability/` | `Tracer` protocol: `observe` (a span or generation, child of the current one, or the root of a given trace id), `attributes` (trace metadata and tags for the observations opened inside), datasets, dataset runs, `flush`, `shutdown`, `check`. `NullTracer` when the Langfuse keys are not both set, `LangfuseTracer` otherwise; `get_tracer()` builds it once per process from the settings and `set_tracer()` replaces it (tests). Every call is best-effort: a Langfuse failure is logged and never changes the outcome of the observed code, whose own exceptions go through and mark the observation `ERROR`. `trace_url` links a trace through the Langfuse UI's `/trace/{id}` route, which resolves the project |
| `temporal/` | `WorkflowClient` protocol (`start`, `cancel`) with `TemporalWorkflowClient`, so services can be tested with a fake; `SizeGuardCodec` and `data_converter()` shared with the worker so the 128 KB payload limit holds on both sides; `workflow_ids.py` with the workflow names, task queues and deterministic workflow ids that the API computes when starting a workflow and the worker re-exports |

Services depend on the protocols (`ObjectStorage`, `WorkflowClient`, `Tracer`), never on S3 or Temporal
directly; `dependencies.py` wires the real implementations.
