---
name: keep-docs-in-sync
description: Documentation guardrail. Use whenever you create or modify code, configuration, routes, components, environment variables, Docker Compose services, scripts or the frontend, to update the READMEs that describe them in the same change.
---

# Keep the documentation in sync

A change is not finished until the documentation that describes it is correct. Update the
docs in the same change, never "later".

## Which README to touch

| If you change... | Update |
|---|---|
| Startup steps, prerequisites, Compose services/profiles, ports, `.env.example`, repository layout | `README.md` (root) |
| A route, a service, a hash, a table, a module's responsibility | `backend/README.md` and `backend/src/<module>/README.md` |
| A builtin component (parser, chunker, embedder, vector store) | `backend/src/components/README.md`, `temporal/components/README.md`, and the component tables in `backend/README.md`, `temporal/README.md` and the root `README.md` |
| A workflow, an activity, a task queue, a timeout, the worker | `temporal/README.md` and `temporal/{workflows,activities,components}/README.md` |
| A page, a route of the UI, a frontend command | `frontend/README.md` |
| The database schema (new migration) | `docs/DATA_MODEL.md` and the module README that owns the table |
| A new module or package | add its `README.md` and link it from the root `README.md` |

## Procedure

1. Before finishing, list the files you changed and map them to the READMEs above.
2. Re-read the affected README sections against the code (route paths, keys, defaults, env
   var names) and fix what no longer matches: do not only append.
3. Remove statements that became false; do not leave history ("previously...") in READMEs.
4. If nothing in the docs needed to change, say so explicitly in your final message.

## Rules

- Describe behaviour logically; do not reference chapters of design files, as they change.
- Keep READMEs concise and consistent with the surrounding style (tables for routes/keys).
- `sprint/` files are a historical plan: do not rewrite them to follow the code.
- `frontend/src/api/schema.d.ts` and `openapi.json` are generated: regenerate, do not edit.
