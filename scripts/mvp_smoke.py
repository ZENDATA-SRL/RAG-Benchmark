"""End-to-end verification of the backend MVP, over HTTP only.

Runs the whole chunking flow against a live stack: create a corpus, upload three PDFs,
create the parsing and chunking profiles, compose the configuration, preview on one
document, materialise the rest, follow the progress by polling, then read back the parse
and the chunks. With `--embedder`, it goes on to freeze a snapshot, build an index on it
and query that index with a known sentence, then import a question set with gold files,
run a retrieval experiment with two variants and read the document-level metrics, confirm
the evidence chunk of one question and re-evaluate the run for its chunk-level metrics.
Every step asserts what the API promised, and the first deviation exits non-zero with the
reason.

Needs the compose services, the API and the Temporal worker running:

    docker compose up -d
    uv run uvicorn src.main:app --app-dir backend --port 8000
    uv run python -m temporal.worker
    uv run python scripts/mvp_smoke.py
    uv run python scripts/mvp_smoke.py --embedder openai --vector-store qdrant

The retrieval part is opt-in because it calls a real embedding model: it needs the
credentials of that embedder in the environment of both the worker and the API.
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import time
from pathlib import Path
from typing import Any

import httpx

# The script drives the API from outside, but reuses the component keys and the PDF builder
# rather than restating them: a smoke test that hardcodes `"pypdf"` stops catching a rename.
# Absolute, so the script runs from any working directory.
_ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(_ROOT / "backend"), str(_ROOT)]


# The three documents the run covers. The text is known so the parse preview can be checked
# against it instead of merely being non-empty, and each page is long enough that a 400 and a
# 1200 character chunk size genuinely disagree: on a two-line PDF they would not.
def _page(opening: str, topic: str) -> str:
    """One page: a distinctive opening sentence, then enough prose to be worth chunking."""
    filler = " ".join(
        f"{topic} consideration number {index} affects how the passage is retrieved "
        f"and how much surrounding context the reader is given."
        for index in range(1, 9)
    )
    return f"{opening} {filler}"


DOCUMENTS: dict[str, list[str]] = {
    "handbook.pdf": [
        _page("Chapter one. The retrieval pipeline starts with parsing.", "Parsing"),
        _page("Chapter two. Chunking decides what the retriever can find.", "Chunking"),
        _page("Chapter three. Evaluation needs the same chunks twice.", "Evaluation"),
    ],
    "policy.pdf": [
        _page(
            "Expenses are reimbursed within thirty days of submission.", "Reimbursement"
        ),
        _page("Travel above five hundred euro requires prior approval.", "Approval"),
    ],
    "faq.pdf": [
        _page("How do I reset my password? Use the self-service portal.", "Account"),
    ],
}

CHUNK_SIZE = 400
OVERLAP = 40
POLL_INTERVAL_SECONDS = 2.0
POLL_TIMEOUT_SECONDS = 180.0
INDEX_TIMEOUT_SECONDS = 600.0
RUN_TIMEOUT_SECONDS = 300.0

# A sentence known to open the second page of policy.pdf: querying it must bring that
# document back first.
RETRIEVAL_QUERY = "Travel above five hundred euro requires prior approval."
RETRIEVAL_DOCUMENT = "policy.pdf"

# Questions of the experiment: the sentence that opens a page of each document, so a sound
# retriever puts that document first. The last row names a file the corpus does not have and
# must be reported, not imported.
EXPERIMENT_QUESTIONS: list[tuple[str, str]] = [
    ("Travel above five hundred euro requires prior approval.", "policy.pdf"),
    ("Chapter two. Chunking decides what the retriever can find.", "handbook.pdf"),
    ("How do I reset my password? Use the self-service portal.", "faq.pdf"),
]
UNRESOLVED_QUESTION = ("Who wrote the missing annex?", "ghost.pdf")

_step = 0


class SmokeFailure(RuntimeError):
    """A step did not deliver what the API contract promises."""


def step(title: str) -> None:
    global _step
    _step += 1
    print(f"\n\033[1m[{_step}] {title}\033[0m")


def ok(message: str) -> None:
    print(f"    \033[32mok\033[0m  {message}")


def check(condition: bool, message: str) -> None:
    """Assert one promise of the API, naming it either way."""
    if not condition:
        raise SmokeFailure(message)
    ok(message)


def request(
    client: httpx.Client, method: str, url: str, *, expect: int = 200, **kwargs: Any
) -> Any:
    """Call the API and fail loudly on an unexpected status, showing the body."""
    response = client.request(method, url, **kwargs)
    if response.status_code != expect:
        raise SmokeFailure(
            f"{method} {url} returned {response.status_code}, expected {expect}: "
            f"{response.text[:500]}"
        )
    if response.status_code == 204:
        return None
    return response.json()


# --------------------------------------------------------------------------------------
# Steps
# --------------------------------------------------------------------------------------


def create_corpus(client: httpx.Client) -> str:
    step("Create the corpus")
    corpus = request(
        client,
        "POST",
        "/corpora",
        expect=201,
        json={
            "name": f"smoke {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "description": "created by scripts/mvp_smoke.py",
        },
    )
    ok(f"corpus {corpus['id']}")
    return corpus["id"]


def upload_documents(client: httpx.Client, corpus_id: str) -> dict[str, str]:
    from temporal.tests.pdf_fixtures import make_pdf

    step("Upload the documents into the corpus")
    files = [
        ("files", (filename, make_pdf(pages), "application/pdf"))
        for filename, pages in DOCUMENTS.items()
    ]
    upload = request(
        client, "POST", f"/corpora/{corpus_id}/documents/upload", files=files
    )

    by_filename = {result["filename"]: result for result in upload["results"]}
    check(
        len(by_filename) == len(DOCUMENTS),
        f"the upload reported one result per file ({len(by_filename)})",
    )
    rejected = {
        filename: result["error_reason"]
        for filename, result in by_filename.items()
        if result["document_id"] is None
    }
    check(not rejected, f"every file was accepted (rejected: {rejected})")

    document_ids = {
        filename: result["document_id"] for filename, result in by_filename.items()
    }
    listing = request(client, "GET", f"/corpora/{corpus_id}/documents")
    check(
        listing["total"] == len(DOCUMENTS),
        f"the corpus holds {listing['total']} documents",
    )
    return document_ids


def component_versions(client: httpx.Client) -> tuple[str, str]:
    from src.components.builtin.chunkers import recursive
    from src.components.builtin.parsers import pypdf

    step("Resolve the builtin components")
    components = request(client, "GET", "/components")
    by_key = {component["key"]: component for component in components}
    for key in (pypdf.KEY, recursive.KEY):
        check(key in by_key, f"the registry exposes {key}")
        check(bool(by_key[key]["versions"]), f"{key} has at least one version")
    return by_key[pypdf.KEY]["versions"][0]["id"], by_key[recursive.KEY]["versions"][0][
        "id"
    ]


def create_profiles(
    client: httpx.Client, parser_version: str, chunker_version: str
) -> None:
    step("Create the profiles, and prove the deduplication is declared")
    first = request(
        client,
        "POST",
        "/parsing-profiles",
        expect=201,
        json={
            "name": "pypdf smoke",
            "component_version_id": parser_version,
            "params": {},
        },
    )
    # Not asserted as `created: true`: the profile is keyed on the parameters and shared by
    # every corpus, so a second run of this script legitimately finds the row already there.
    ok(
        f"parsing profile {first['profile']['id']} "
        f"({'created' if first['created'] else 'already existed'})"
    )

    # Same parameters, different name: the hash excludes the name, so the original
    # row comes back and the response must say so, or the user cannot explain the mismatch.
    again = request(
        client,
        "POST",
        "/parsing-profiles",
        expect=201,
        json={
            "name": "a completely different name",
            "component_version_id": parser_version,
            "params": {},
        },
    )
    check(
        again["created"] is False,
        "the identical profile was reused rather than duplicated",
    )
    check(
        again["profile"]["id"] == first["profile"]["id"],
        "the reused profile has the same id",
    )
    check(
        again["profile"]["name"] == first["profile"]["name"],
        f"the name returned is the original one ({again['profile']['name']!r})",
    )

    rejected = request(
        client,
        "POST",
        "/parsing-profiles",
        expect=422,
        json={
            "name": "invalid",
            "component_version_id": parser_version,
            "params": {"extract_images": "yes please"},
        },
    )
    check(
        rejected["code"] == "invalid_component_params",
        "parameters outside the schema are refused server-side",
    )
    check(
        "field_path" in rejected["details"], "the rejection names the offending field"
    )


def compose_configuration(
    client: httpx.Client, parser_version: str, chunker_version: str, *, chunk_size: int
) -> str:
    from src.components.builtin.chunkers import recursive

    step(f"Compose the chunking configuration (chunk_size={chunk_size})")
    composed = request(
        client,
        "POST",
        "/chunking-configurations/compose",
        expect=201,
        json={
            "parsing_component_version_id": parser_version,
            "parsing_profile_name": "pypdf smoke",
            "chunking_component_version_id": chunker_version,
            "chunking_profile_name": f"recursive {chunk_size}",
            "chunking_strategy": recursive.STRATEGY,
            "chunk_size": chunk_size,
            "overlap": OVERLAP,
        },
    )
    configuration = composed["configuration"]
    check(
        configuration["parsing_profile"]["id"] is not None
        and configuration["chunking_profile"]["chunk_size"] == chunk_size,
        "the configuration comes back with both profiles expanded",
    )
    ok(f"configuration {configuration['id']}")
    return configuration["id"]


def materialize(
    client: httpx.Client,
    *,
    configuration_id: str,
    corpus_id: str | None = None,
    document_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Launch a run and wait for it to reach a terminal state."""
    payload: dict[str, Any] = {"chunking_configuration_id": configuration_id}
    if document_ids is not None:
        payload["document_ids"] = document_ids
    if corpus_id is not None:
        payload["corpus_id"] = corpus_id
    accepted = request(client, "POST", "/materializations", expect=202, json=payload)
    # Not asserted as `started`: the workflow id is a function of the configuration and the
    # document set, so a repeat of this script joins the run it launched last time. That is
    # the idempotency of the workflow id, and step "launch the same work twice" checks it explicitly.
    ok(
        f"run {accepted['id']} "
        f"({'started' if accepted['started'] else 'already in flight, following it'})"
    )
    return poll_until_finished(client, accepted["id"])


def poll_until_finished(client: httpx.Client, run_id: str) -> dict[str, Any]:
    """Follow a run the way the UI does: `GET` every couple of seconds."""
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    last = ""
    while True:
        run = request(client, "GET", f"/materializations/{run_id}")
        progress = run["progress"]
        line = (
            f"{run['status']}: ready={progress['ready']} cached={progress['cached']} "
            f"failed={progress['failed']} pending={progress['pending']}"
        )
        if line != last:
            print(f"    ..  {line}")
            last = line
        if run["status"] in ("ready", "failed"):
            return run
        if time.monotonic() > deadline:
            raise SmokeFailure(
                f"run {run_id} still {run['status']} after {POLL_TIMEOUT_SECONDS:.0f}s "
                f"({line}); is the Temporal worker running?"
            )
        time.sleep(POLL_INTERVAL_SECONDS)


def preview_one_document(
    client: httpx.Client, *, configuration_id: str, document_id: str
) -> None:
    step("Preview the configuration on a single document")
    run = materialize(
        client, configuration_id=configuration_id, document_ids=[document_id]
    )
    check(run["document_count"] == 1, "the preview covered exactly one document")
    check(
        run["status"] == "ready",
        f"the preview succeeded (failures: {run['failures']})",
    )
    # Either freshly chunked or served from cache: the artefact is keyed on content, so a
    # second run of this script re-uses the chunks the first one produced.
    check(
        run["progress"]["ready"] + run["progress"]["cached"] == 1,
        "the document came out chunked",
    )


def materialize_corpus(
    client: httpx.Client, *, configuration_id: str, corpus_id: str
) -> dict[str, Any]:
    step("Materialise the whole corpus")
    run = materialize(client, configuration_id=configuration_id, corpus_id=corpus_id)
    check(
        run["document_count"] == len(DOCUMENTS),
        f"the run covered every document of the corpus ({run['document_count']})",
    )
    check(
        run["status"] == "ready",
        f"the run finished ready (failures: {run['failures']})",
    )
    # The preview already chunked one of them, and its artefact is content-addressed: the
    # corpus run must reuse it rather than redo the work.
    check(
        run["progress"]["cached"] >= 1,
        f"the previewed document was served from cache ({run['progress']['cached']})",
    )
    check(
        run["progress"]["ready"] + run["progress"]["cached"] == len(DOCUMENTS),
        "every document is accounted for as either chunked or cached",
    )
    return run


def check_idempotent_launch(
    client: httpx.Client, *, configuration_id: str, corpus_id: str
) -> None:
    step("Launch the same work twice in a row")
    payload = {"chunking_configuration_id": configuration_id, "corpus_id": corpus_id}
    first = request(client, "POST", "/materializations", expect=202, json=payload)
    second = request(client, "POST", "/materializations", expect=202, json=payload)
    check(
        first["id"] == second["id"],
        "the two launches report the same run, so a double click is not an error",
    )
    check(
        first["workflow_id"] == second["workflow_id"],
        "and the same workflow, because the id is a function of the document set",
    )
    poll_until_finished(client, first["id"])


def check_coverage(
    client: httpx.Client, *, configuration_id: str, corpus_id: str
) -> None:
    step("Ask whether the configuration is ready on the corpus")
    coverage = request(
        client,
        "GET",
        f"/chunking-configurations/{configuration_id}/coverage",
        params={"corpus_id": corpus_id},
    )
    check(
        coverage["ready"] + coverage["failed"] + coverage["missing"]
        == coverage["total"],
        f"the three counts sum to the corpus size ({coverage['total']})",
    )
    check(
        coverage["total"] == len(DOCUMENTS),
        "the total is the number of uploaded documents",
    )
    check(coverage["missing"] == 0, "no document is left unmaterialised")
    check(
        coverage["is_complete"] is True, "the configuration is complete on this corpus"
    )


def check_parse_preview(
    client: httpx.Client, *, configuration_id: str, document_ids: dict[str, str]
) -> None:
    step("Read the parse back, page by page (4.5)")
    configuration = request(
        client, "GET", f"/chunking-configurations/{configuration_id}"
    )
    parsing_profile_id = configuration["parsing_profile"]["id"]

    filename = "handbook.pdf"
    pages = DOCUMENTS[filename]
    parse = request(
        client,
        "GET",
        f"/documents/{document_ids[filename]}/parse",
        params={"parsing_profile_id": parsing_profile_id},
    )
    check(
        parse["total"] == len(pages),
        f"{filename} parsed into {parse['total']} pages, as authored",
    )

    # Page 3 specifically: what matters is that the text of a given page is the
    # text of that page, not merely that something came back.
    third = request(
        client,
        "GET",
        f"/documents/{document_ids[filename]}/parse",
        params={"parsing_profile_id": parsing_profile_id, "limit": 1, "offset": 2},
    )
    check(len(third["items"]) == 1, "asking for one page returns one page")
    page = third["items"][0]
    expected = pages[2].rstrip(".")
    check(
        expected.split(".")[0] in page["text"],
        f"page {page['page']} contains the text authored on page 3",
    )


def check_chunks(
    client: httpx.Client, *, configuration_id: str, document_ids: dict[str, str]
) -> dict[str, Any]:
    step("List the chunks of a document")
    document_id = document_ids["handbook.pdf"]
    chunks = request(
        client,
        "GET",
        f"/documents/{document_id}/chunks",
        params={"chunking_configuration_id": configuration_id},
    )
    check(chunks["total"] > 0, f"the document produced {chunks['total']} chunks")
    check(
        chunks["total"] > 1,
        "a document longer than the chunk size was split into several chunks",
    )
    check(
        chunks["chunk_result"]["status"] == "ready",
        "the artefact holding them is ready",
    )
    check(
        chunks["chunk_result"]["chunk_count"] == chunks["total"],
        "the artefact's chunk count matches the number of rows",
    )

    ordinals = [chunk["ordinal"] for chunk in chunks["items"]]
    check(ordinals == sorted(ordinals), "the chunks come back in ordinal order")
    check(
        ordinals == list(range(len(ordinals))), "the ordinals are contiguous from zero"
    )
    check(
        all(chunk["text"].strip() for chunk in chunks["items"]),
        "every chunk carries text",
    )
    check(
        all("page" in chunk["metadata"] for chunk in chunks["items"]),
        "every chunk carries the page it came from",
    )

    first = chunks["items"][0]
    detail = request(client, "GET", f"/chunks/{first['id']}")
    check(detail["text"] == first["text"], "a single chunk is readable by id")

    if chunks["total"] > 1:
        page = request(
            client,
            "GET",
            f"/documents/{document_id}/chunks",
            params={
                "chunking_configuration_id": configuration_id,
                "limit": 1,
                "offset": 1,
            },
        )
        check(
            page["items"][0]["ordinal"] == 1 and page["total"] == chunks["total"],
            "pagination moves the window without changing the total",
        )
    return chunks


def check_two_configurations_differ(
    client: httpx.Client,
    *,
    document_ids: dict[str, str],
    parser_version: str,
    chunker_version: str,
    first_configuration: str,
) -> None:
    step("Chunk the same document under a second configuration and compare")
    second_configuration = compose_configuration(
        client, parser_version, chunker_version, chunk_size=CHUNK_SIZE * 3
    )
    document_id = document_ids["handbook.pdf"]
    run = materialize(
        client, configuration_id=second_configuration, document_ids=[document_id]
    )
    check(run["status"] == "ready", "the second configuration materialised")
    # The parse is shared: only the chunking profile changed, so this must have been a cache
    # hit at the parsing stage and real work only at the chunking one.
    comparison = request(
        client,
        "GET",
        f"/documents/{document_id}/chunks/compare",
        params={"configurations": f"{first_configuration},{second_configuration}"},
    )
    sides = comparison["sides"]
    check(len(sides) == 2, "the comparison returns both sides")
    left = [chunk["text"] for chunk in sides[0]["chunks"]]
    right = [chunk["text"] for chunk in sides[1]["chunks"]]
    check(
        left != right,
        f"a larger chunk size produces different chunks ({len(left)} vs {len(right)})",
    )


def check_history(client: httpx.Client, *, configuration_id: str, run_id: str) -> int:
    step("Read the run history")
    history = request(
        client,
        "GET",
        "/materializations",
        params={"chunking_configuration_id": configuration_id},
    )
    check(
        history["total"] >= 1,
        f"the configuration has {history['total']} run(s) on record",
    )
    check(
        all(
            run["chunking_configuration_id"] == configuration_id
            for run in history["items"]
        ),
        "the filter returns only this configuration's runs",
    )
    # Filtered by configuration rather than by corpus: the workflow id is a function of the
    # configuration and the document set, so re-running this script joins the row the previous
    # one opened, and that row keeps the corpus it was first launched for.
    check(
        any(run["id"] == run_id for run in history["items"]),
        "the corpus run just followed appears in the history",
    )
    return history["total"]


# --------------------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------------------


def check_retrieval(
    client: httpx.Client,
    *,
    corpus_id: str,
    configuration_id: str,
    embedder: str,
    vector_store: str,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Build an index over the corpus and query it with a sentence of a known document.

    Returns the result of the query and the ids the experiment reuses: the corpus snapshot,
    the index build and the retrieval profile.
    """
    step("Freeze a snapshot of the corpus")
    snapshot = request(
        client,
        "POST",
        f"/corpora/{corpus_id}/snapshots",
        json={"label": "smoke"},
        expect=201,
    )["snapshot"]
    ok(f"snapshot {snapshot['id']}")

    step(f"Create the {embedder} embedding and {vector_store} vector store profiles")
    components = request(client, "GET", "/components")
    versions = {
        (component["type"], component["key"]): component["versions"][0]["id"]
        for component in components
        if component["versions"]
    }
    for identity in (("embedder", embedder), ("vector_store", vector_store)):
        check(identity in versions, f"the registry exposes {identity[0]} {identity[1]}")
    embedding = request(
        client,
        "POST",
        "/embedding-profiles",
        json={
            "name": f"smoke {embedder}",
            "component_version_id": versions[("embedder", embedder)],
            "modality": "text",
            "params": {},
        },
        expect=201,
    )["profile"]
    store = request(
        client,
        "POST",
        "/vector-store-profiles",
        json={
            "name": f"smoke {vector_store}",
            "component_version_id": versions[("vector_store", vector_store)],
            "index_params": {"space": "cosine"},
        },
        expect=201,
    )["profile"]

    step("Build the index")
    build = request(
        client,
        "POST",
        "/index-builds",
        json={
            "corpus_snapshot_id": snapshot["id"],
            "chunking_configuration_id": configuration_id,
            "embedding_profile_id": embedding["id"],
            "vector_store_profile_id": store["id"],
        },
        expect=201,
    )["index_build"]
    request(client, "POST", f"/index-builds/{build['id']}/start", expect=202)
    deadline = time.monotonic() + INDEX_TIMEOUT_SECONDS
    while True:
        detail = request(client, "GET", f"/index-builds/{build['id']}")
        if detail["status"] in ("ready", "failed"):
            break
        if time.monotonic() > deadline:
            raise SmokeFailure(
                f"index build {build['id']} still {detail['status']} after "
                f"{INDEX_TIMEOUT_SECONDS:.0f}s; is the Temporal worker running?"
            )
        time.sleep(POLL_INTERVAL_SECONDS)
    check(
        detail["status"] == "ready",
        f"index build ready with {detail['chunk_count']} chunks",
    )

    step("Create a retrieval profile, and prove unsupported features are refused")
    profile = request(
        client,
        "POST",
        "/retrieval-profiles",
        json={"name": "smoke top3", "top_k": 3},
        expect=201,
    )["profile"]
    refused = request(
        client,
        "POST",
        "/retrieval-profiles",
        json={"name": "smoke hybrid", "top_k": 3, "strategy": "hybrid"},
        expect=422,
    )
    check(
        refused["code"] == "unsupported_retrieval_feature",
        "a hybrid strategy is refused instead of stored",
    )

    step("Query the index with a sentence of a known document")
    body = {
        "index_build_id": build["id"],
        "retrieval_profile_id": profile["id"],
        "query": RETRIEVAL_QUERY,
    }
    result = request(client, "POST", "/retrieve", json=body)
    hits = result["hits"]
    check(bool(hits), f"{len(hits)} hits in {result['timings']['total_ms']:.0f} ms")
    check(
        [hit["rank"] for hit in hits] == list(range(1, len(hits) + 1)),
        "ranks start at 1",
    )
    check(
        hits[0]["filename"] == RETRIEVAL_DOCUMENT
        and RETRIEVAL_QUERY in (hits[0]["text"] or ""),
        f"the first hit is the chunk of {RETRIEVAL_DOCUMENT} holding the sentence",
    )
    again = request(client, "POST", "/retrieve", json=body)
    check(
        [hit["chunk_id"] for hit in again["hits"]] == [hit["chunk_id"] for hit in hits],
        "the same query returns the same chunks",
    )
    return result, {
        "corpus_snapshot_id": snapshot["id"],
        "index_build_id": build["id"],
        "retrieval_profile_id": profile["id"],
    }


def _questions_csv(rows: list[tuple[str, str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["question", "gold_files", "tags", "answerable"])
    for question, gold_file in rows:
        writer.writerow([question, gold_file, "smoke", "true"])
    return buffer.getvalue().encode()


def _variants(results: dict[str, Any]) -> list[dict[str, Any]]:
    """The variants of every chunking configuration group of a run's results."""
    return [variant for group in results["groups"] for variant in group["variants"]]


def check_experiment(
    client: httpx.Client, *, corpus_id: str, context: dict[str, str]
) -> dict[str, Any]:
    """Import a question set, run a two-variant retrieval experiment and read its metrics."""
    step("Create a question set and import questions with their gold files")
    qa_set = request(
        client,
        "POST",
        "/qa-sets",
        json={"name": "smoke questions", "origin_corpus_id": corpus_id},
        expect=201,
    )
    content = _questions_csv([*EXPERIMENT_QUESTIONS, UNRESOLVED_QUESTION])
    summary = request(
        client,
        "POST",
        f"/qa-sets/{qa_set['id']}/import",
        files={"file": ("questions.csv", content, "text/csv")},
    )
    check(
        len(summary["imported"]) == len(EXPERIMENT_QUESTIONS),
        f"{len(summary['imported'])} questions imported",
    )
    check(
        [row["question"] for row in summary["unresolved"]] == [UNRESOLVED_QUESTION[0]],
        "the question naming a missing file is reported, not imported",
    )
    again = request(
        client,
        "POST",
        f"/qa-sets/{qa_set['id']}/import",
        files={"file": ("questions.csv", content, "text/csv")},
    )
    check(
        again["imported"] == [] and len(again["existing"]) == len(EXPERIMENT_QUESTIONS),
        "importing the same file again adds no question",
    )

    step("Freeze the question set")
    frozen = request(
        client, "POST", f"/qa-sets/{qa_set['id']}/snapshots", json={}, expect=201
    )
    qa_snapshot = frozen["snapshot"]
    check(
        qa_snapshot["question_count"] == len(EXPERIMENT_QUESTIONS),
        f"snapshot of {qa_snapshot['question_count']} questions",
    )
    twice = request(
        client, "POST", f"/qa-sets/{qa_set['id']}/snapshots", json={}, expect=201
    )
    check(
        twice["snapshot"]["id"] == qa_snapshot["id"] and not twice["created"],
        "freezing the same questions again returns the same snapshot",
    )

    step("Create the experiment: two variants on the same index, top-3 against top-5")
    wide = request(
        client,
        "POST",
        "/retrieval-profiles",
        json={"name": "smoke top5", "top_k": 5},
        expect=201,
    )["profile"]
    experiment = request(
        client,
        "POST",
        "/experiments",
        json={
            "name": "smoke retrieval",
            "type": "retrieval",
            "corpus_snapshot_id": context["corpus_snapshot_id"],
            "qa_set_snapshot_id": qa_snapshot["id"],
            "variants": [
                {
                    "name": "top-3",
                    "index_build_id": context["index_build_id"],
                    "retrieval_profile_id": context["retrieval_profile_id"],
                    "is_baseline": True,
                },
                {
                    "name": "top-5",
                    "index_build_id": context["index_build_id"],
                    "retrieval_profile_id": wide["id"],
                },
            ],
        },
        expect=201,
    )
    check(
        experiment["coverage"]["uncovered_count"] == 0,
        "every gold file is in the snapshot",
    )

    step("Run the experiment")
    base = f"/experiments/{experiment['id']}"
    run = request(client, "POST", f"{base}/runs", json={}, expect=202)
    deadline = time.monotonic() + RUN_TIMEOUT_SECONDS
    while True:
        detail = request(client, "GET", f"{base}/runs/{run['id']}")
        if detail["status"] in ("succeeded", "failed"):
            break
        if time.monotonic() > deadline:
            raise SmokeFailure(
                f"run {run['id']} still {detail['status']} after "
                f"{RUN_TIMEOUT_SECONDS:.0f}s; is the Temporal worker running?"
            )
        time.sleep(POLL_INTERVAL_SECONDS)
    check(detail["status"] == "succeeded", f"run succeeded: {detail['progress']}")
    check(
        detail["progress"]["succeeded"] == 2 * len(EXPERIMENT_QUESTIONS),
        "every question was executed on every variant",
    )

    step("Read the document-level metrics")
    results = request(client, "GET", f"{base}/runs/{run['id']}/results")
    check(
        results["corpus_snapshot"]["id"] == context["corpus_snapshot_id"],
        "the result declares the corpus snapshot it was measured on",
    )
    for variant in _variants(results):
        metrics = {metric["key"]: metric for metric in variant["metrics"]}
        recall = metrics["recall@5"]
        check(
            recall["n_effective"] + recall["n_excluded"] == len(EXPERIMENT_QUESTIONS),
            f"{variant['name']}: {recall['n_effective']} effective + "
            f"{recall['n_excluded']} excluded questions",
        )
        check(
            metrics["mrr"]["mean"] == 1.0,
            f"{variant['name']}: the gold document is always first (mrr 1.0)",
        )

    step("Open a question and download the results")
    questions = request(client, "GET", f"{base}/runs/{run['id']}/questions")
    question_id = questions["items"][0]["question_id"]
    drilldown = request(
        client, "GET", f"{base}/runs/{run['id']}/questions/{question_id}"
    )
    check(
        all(
            variant["executions"][0]["hits"][0]["relevant_document"]
            for variant in drilldown["variants"]
        ),
        "each variant's first hit is flagged as relevant",
    )
    export = client.get(f"{base}/runs/{run['id']}/results.csv")
    check(
        export.status_code == 200
        and export.text.startswith("chunking_configuration_id,variant,"),
        "the results download as CSV, with the configuration and level of each row",
    )
    return check_chunk_metrics(
        client, base=base, run_id=run["id"], drilldown=drilldown, before=results
    )


def check_chunk_metrics(
    client: httpx.Client,
    *,
    base: str,
    run_id: str,
    drilldown: dict[str, Any],
    before: dict[str, Any],
) -> dict[str, Any]:
    """Confirm the evidence chunk of one question, re-evaluate the run, read the chunk metrics."""
    step("Confirm the evidence of one question and re-evaluate the run")
    variant = drilldown["variants"][0]
    top_hit = variant["executions"][0]["hits"][0]
    request(
        client,
        "PUT",
        f"/questions/{drilldown['question_id']}/evidence",
        json={
            "chunking_configuration_id": variant["chunking_configuration_id"],
            "status": "confirmed",
            "annotator": "smoke",
            "chunks": [{"chunk_id": top_hit["chunk_id"], "relevance": "sufficient"}],
        },
    )
    evaluated = request(client, "POST", f"{base}/runs/{run_id}/evaluate")
    check(
        bool(evaluated["config_snapshot"]["chunk_gold"]["hash"]),
        "the run records the fingerprint of the evidence it was scored on",
    )
    results = request(client, "GET", f"{base}/runs/{run_id}/results")
    group = results["groups"][0]
    check(
        group["evidence_coverage"]["confirmed"] == 1 and group["recall_ceiling"] == 1.0,
        "one confirmed question, nothing marked not found: recall ceiling 1.0",
    )
    recall_before = {
        variant["name"]: {m["key"]: m for m in variant["metrics"]}["recall@5"]
        for variant in _variants(before)
    }
    for variant in _variants(results):
        metrics = {metric["key"]: metric for metric in variant["metrics"]}
        chunk_mrr = metrics["chunk_mrr"]
        check(
            chunk_mrr["n_effective"] == 1 and chunk_mrr["mean"] == 1.0,
            f"{variant['name']}: the confirmed chunk comes first (chunk_mrr 1.0, 1 question)",
        )
        check(
            metrics["recall@5"] == recall_before[variant["name"]],
            f"{variant['name']}: the document-level metrics did not change",
        )
    return results


def run(base_url: str, *, embedder: str | None, vector_store: str) -> None:
    root = base_url.rstrip("/")
    with httpx.Client(base_url=f"{root}/api/v1", timeout=120.0) as client:
        step("Check the API is up")
        health = request(client, "GET", f"{root}/health")
        ok(f"health: {health}")

        corpus_id = create_corpus(client)
        document_ids = upload_documents(client, corpus_id)
        parser_version, chunker_version = component_versions(client)
        create_profiles(client, parser_version, chunker_version)
        configuration_id = compose_configuration(
            client, parser_version, chunker_version, chunk_size=CHUNK_SIZE
        )

        preview_one_document(
            client,
            configuration_id=configuration_id,
            document_id=document_ids["handbook.pdf"],
        )
        corpus_run = materialize_corpus(
            client, configuration_id=configuration_id, corpus_id=corpus_id
        )
        check_idempotent_launch(
            client, configuration_id=configuration_id, corpus_id=corpus_id
        )
        check_coverage(client, configuration_id=configuration_id, corpus_id=corpus_id)
        check_parse_preview(
            client, configuration_id=configuration_id, document_ids=document_ids
        )
        chunks = check_chunks(
            client, configuration_id=configuration_id, document_ids=document_ids
        )
        check_two_configurations_differ(
            client,
            document_ids=document_ids,
            parser_version=parser_version,
            chunker_version=chunker_version,
            first_configuration=configuration_id,
        )
        runs = check_history(
            client, configuration_id=configuration_id, run_id=corpus_run["id"]
        )
        retrieval = None
        experiment = None
        if embedder:
            retrieval, context = check_retrieval(
                client,
                corpus_id=corpus_id,
                configuration_id=configuration_id,
                embedder=embedder,
                vector_store=vector_store,
            )
            experiment = check_experiment(client, corpus_id=corpus_id, context=context)

        print("\n\033[1;32mMVP smoke passed\033[0m")
        print(f"    corpus            {corpus_id}")
        print(f"    documents         {len(document_ids)}")
        print(f"    configuration     {configuration_id}")
        print(f"    runs recorded     {runs}")
        print(f"    chunks (handbook) {chunks['total']}")
        print("\n    Sample of the first chunk:")
        sample = chunks["items"][0]
        text = sample["text"].replace("\n", " ")
        print(
            f"      #{sample['ordinal']} p{sample['metadata'].get('page')} {text[:90]}"
        )
        if retrieval is None:
            print(
                "\n    Retrieval and experiment skipped: pass --embedder to build and "
                "query an index."
            )
        else:
            first = retrieval["hits"][0]
            print(f"\n    Top hit for {RETRIEVAL_QUERY!r}:")
            print(f"      {first['score']:.3f} {first['filename']} p{first['page']}")
        if experiment is not None:
            print("\n    Experiment metrics (recall@5, n effective of n total):")
            for variant in _variants(experiment):
                recall = {m["key"]: m for m in variant["metrics"]}["recall@5"]
                total = recall["n_effective"] + recall["n_excluded"]
                print(
                    f"      {variant['name']:<8} {recall['mean']:.2f} "
                    f"({recall['n_effective']} of {total})"
                )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Where the API is listening (default: %(default)s)",
    )
    parser.add_argument(
        "--embedder",
        choices=["openai", "bedrock"],
        help="Also build an index with this embedder and query it (needs its credentials)",
    )
    parser.add_argument(
        "--vector-store",
        choices=["chromadb", "qdrant"],
        default="chromadb",
        help="Vector store of the index built with --embedder (default: %(default)s)",
    )
    arguments = parser.parse_args()

    try:
        run(
            arguments.base_url,
            embedder=arguments.embedder,
            vector_store=arguments.vector_store,
        )
    except SmokeFailure as failure:
        print(f"\n\033[1;31mMVP smoke failed\033[0m\n    {failure}", file=sys.stderr)
        return 1
    except httpx.HTTPError as error:
        print(
            f"\n\033[1;31mMVP smoke failed\033[0m\n    cannot reach {arguments.base_url}: "
            f"{error}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
