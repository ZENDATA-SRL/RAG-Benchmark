# core

Cross-cutting utilities with no dependency on any domain module.

| File | Provides |
|---|---|
| `hashing.py` | The hashes that identify every artefact: `hash_parts`, `hash_json` (canonical, key-order independent), `config_hash`, `combined_config_hash`, `cache_key`, `composition_hash`, `chain_fingerprint` |
| `get_or_create.py` | `get_or_create` / `get_or_create_reporting`: lookup, insert, and recover from a unique violation raised by a concurrent writer. The reporting variant also returns whether the row was created |
| `exceptions.py` | `DomainError` and its HTTP-mapped subclasses `NotFoundError` (404), `ConflictError`, `ValidationError`, `UnsupportedOperationError`. Each carries a stable `code` the UI branches on; one handler in `main.py` serialises them all |
| `pagination.py` | `Page[T]` response envelope (`items`, `total`, `limit`, `offset`) |
| `logging.py` | Log configuration and a request-id filter fed by the middleware in `main.py` |

Domain modules define their own errors by subclassing these (see each module's `exceptions.py`).
