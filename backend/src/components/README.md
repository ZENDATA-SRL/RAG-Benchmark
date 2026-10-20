# components

Registry of pluggable components (parser, chunker, embedder, vector store, ...) and their
versions. A profile in `pipelines/` always points at a `component_versions` row.

| File | Role |
|---|---|
| `models.py` | `Component` (type + key) and `ComponentVersion` (version, runtime, `params_schema`, `capabilities`, availability) |
| `service.py` | `ComponentService`: `register_component`, `register_version`, `validate_params` (JSON Schema), `mark_unavailable` / `mark_available`, listing |
| `repository.py` | Data access |
| `router.py` | `GET /components` (feeds the UI forms), `POST /components`, version registration, availability toggles |
| `schemas.py`, `exceptions.py` | DTOs and errors (`InvalidComponentParamsError`, `UnknownBuiltinError`, ...) |
| `registry_seed.py` | `seed_builtin_components`: registers every descriptor at startup, idempotently |
| `builtin/` | Declarations of the builtin components, see below |

## builtin/

Declarative only: no parsing or embedding library is imported here, so the API can seed and
serve the registry on its own. The executable code lives in `temporal/components/`.

- `contracts.py`: `Parser` / `Chunker` protocols, `ParseOutput`, `ParsePage`, `ChunkPayload`.
- `__init__.py`: `BuiltinDescriptor` and the descriptor lists (`PARSER_`, `CHUNKER_`,
  `EMBEDDER_`, `VECTOR_STORE_DESCRIPTORS`); `BUILTIN_KEYS` is what `register_version`
  validates a builtin key against.
- One module per component, each exposing `KEY`, `VERSION`, `DISPLAY_NAME`, `PARAMS_SCHEMA`
  (and `CAPABILITIES` for parsers and chunkers): `parsers/{pypdf,pdfplumber}`,
  `chunkers/{recursive,markdown}`, `embedder/{openai_embedder,bedrock_embedder}`,
  `vector_stores/chroma`.

## Adding a builtin component

1. Create the declaration module with `KEY`, `VERSION`, `PARAMS_SCHEMA`.
2. Add a descriptor to the right list in `builtin/__init__.py`.
3. Implement it in `temporal/components/` and register it in `BUILTIN_PARSERS`,
   `BUILTIN_CHUNKERS`, `BUILTIN_VECTOR_STORES` (`components/__init__.py`) or
   `BUILTIN_EMBEDDERS` (`embedders/shared.py`). The worker refuses to start if a declared
   key is missing from these maps.

Changing `PARAMS_SCHEMA` for a released component means bumping `VERSION`: profiles are
hashed on the version id, so editing in place would change what existing hashes mean.
