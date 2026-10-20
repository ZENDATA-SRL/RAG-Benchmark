from __future__ import annotations

import asyncio
import time

import pytest
from temporalio.testing import ActivityEnvironment

from temporal.activities import parsing

pytestmark = pytest.mark.asyncio


async def test_the_parse_heartbeats_while_the_thread_works(monkeypatch) -> None:
    """`activity.heartbeat` needs the event loop, so it cannot run inside the parser thread.

    Regression test: calling it from the thread raised `RuntimeError: no running event loop`
    and killed the activity, leaving the workflow pending until its heartbeat timeout. The
    loop must report liveness *while* the blocking parse occupies its thread (RT-O04).
    """
    monkeypatch.setattr(parsing, "_HEARTBEAT_INTERVAL_SECONDS", 0.01)

    def slow_parser(key, storage_uri, filename, params):
        # Blocks the worker thread the way a real parse does; a heartbeat emitted from here
        # has no running loop to schedule itself on.
        time.sleep(0.15)
        return {"pages": [{"page": 1, "text": "parsed"}]}

    monkeypatch.setattr(parsing, "_run_parser", slow_parser)

    beats: list[float] = []
    environment = ActivityEnvironment()
    environment.on_heartbeat = lambda *args: beats.append(args[0])

    output = await environment.run(
        parsing._parse_with_heartbeat, "pypdf", "s3://bucket/doc.pdf", "doc.pdf", {}
    )

    assert output["pages"][0]["text"] == "parsed"
    assert beats, "the activity never reported liveness while the parse was running"
    assert beats == sorted(beats), "the reported elapsed time must grow"


async def test_a_fast_parse_returns_without_heartbeating(monkeypatch) -> None:
    """A parse that finishes inside one interval needs no heartbeat, and must not stall."""
    monkeypatch.setattr(parsing, "_HEARTBEAT_INTERVAL_SECONDS", 5.0)
    monkeypatch.setattr(
        parsing,
        "_run_parser",
        lambda key, storage_uri, filename, params: {
            "pages": [{"page": 1, "text": "quick"}]
        },
    )

    beats: list[float] = []
    environment = ActivityEnvironment()
    environment.on_heartbeat = lambda *args: beats.append(args[0])

    output = await asyncio.wait_for(
        environment.run(
            parsing._parse_with_heartbeat, "pypdf", "s3://bucket/doc.pdf", "doc.pdf", {}
        ),
        timeout=2.0,
    )

    assert output["pages"][0]["text"] == "quick"
    assert beats == []


async def test_a_parser_failure_reaches_the_caller(monkeypatch) -> None:
    """The error must propagate, so `parse_document` can record it and fail the artefact."""
    monkeypatch.setattr(parsing, "_HEARTBEAT_INTERVAL_SECONDS", 0.01)

    def exploding_parser(key, storage_uri, filename, params):
        raise ValueError("corrupt pdf")

    monkeypatch.setattr(parsing, "_run_parser", exploding_parser)

    with pytest.raises(ValueError, match="corrupt pdf"):
        await ActivityEnvironment().run(
            parsing._parse_with_heartbeat, "pypdf", "s3://bucket/doc.pdf", "doc.pdf", {}
        )
