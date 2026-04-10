"""
Application-wide logging configuration (stdlib ``logging``).

Environment:
  - ``LOG_LEVEL``: root log level (default ``INFO``). Use ``DEBUG`` for
    per-document ingestion detail, blob I/O, and DB pool init.

HTTP request lines come from **uvicorn.access** (not from app middleware).
"""

from __future__ import annotations

import logging.config
import os

_CONFIGURED = False


def configure_logging() -> None:
    """Idempotent: safe to call multiple times (e.g. tests + uvicorn reload)."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    if level_name not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        level_name = "INFO"

    config: dict = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            # Hot-reload file watcher is very chatty during development.
            "watchfiles": {
                "handlers": [],
                "propagate": False,
                "level": "CRITICAL",
            },
            "watchfiles.main": {
                "handlers": [],
                "propagate": False,
                "level": "CRITICAL",
            },
        },
        "root": {
            "level": level_name,
            "handlers": ["console"],
        },
    }

    logging.config.dictConfig(config)
    _CONFIGURED = True
