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
