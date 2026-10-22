# Project guidelines (Zendata Python/FastAPI)

- Follow the repository Python Coding Policy.
- Prefer small, safe, incremental diffs.
- Do not introduce new architectural patterns or new dependencies unless explicitly requested.
- Keep code simple and readable; avoid clever abstractions.
- All Python code must be formatted with ruff: run `ruff format` and `ruff check` on every Python file you create or modify.
- If requirements are ambiguous, make the smallest reasonable assumption and state it.
- Documentation is part of the change: whenever you modify code, configuration, routes, components, env vars, Compose services or the UI, update the READMEs that describe them in the same change (see the `keep-docs-in-sync` skill), and say so if no doc needed updating.
- Do not reference design file chapters as they may change over time. Just provide logical descriptions.

Skills in `.claude/skills/` (`backend-structure`, `python-docstrings`, `keep-docs-in-sync`) hold the detailed backend and docstring rules.
