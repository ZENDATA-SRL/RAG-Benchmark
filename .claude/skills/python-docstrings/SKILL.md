---
name: python-docstrings
description: Docstring conventions (Google style) for Python code. Use when writing or editing Python files, to decide where docstrings are required and how long they should be.
---

# Docstrings

- Style: Google docstring format.
- Required for:
  - public functions/classes in `service.py`
  - `repository.py` when queries are non-trivial
  - reusable infrastructure components (`src/infrastructure/`)
  - non-trivial core modules (`src/core/`)
- Optional for:
  - simple route handlers
  - obvious helpers in `utils.py`
- Keep docstrings short: 1-line summary + details only if useful.
- Docstrings and code must be formatted with ruff (`ruff format`, `ruff check`) after editing.
- Do not write initial file (module) docstrings that reference other documents; only Python components (functions/classes) get docstrings.

## No references to project documents

- Docstrings and comments (Python, TypeScript, YAML, Dockerfile, `.env.example`) describe
  what the code does and why, in plain words.
- Never cite requirement or design identifiers (`RF-…`, `RT-…`), section/chapter numbers,
  sprint or milestone names, "acceptance of 4.1" or "the DoD", nor point to a specific passage
  of `docs/`: they change over time and leave dangling references.
- Instead of "payloads over 128 KB are rejected (RT-O02)", write why the rule exists
  ("large artefacts go to object storage, so workflow payloads stay small").
- Module READMEs may link to `docs/` as a whole, but not to numbered sections of it.
