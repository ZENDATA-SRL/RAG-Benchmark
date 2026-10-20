from __future__ import annotations

import datetime as dt
import uuid

import pytest
from src.documents.models import Document
from src.infrastructure.database.enums import ArtifactStatus, DocumentStatus
from src.infrastructure.temporal.workflow_ids import (
    CHUNKING_TASK_QUEUE,
    MATERIALIZE_CHUNKS_WORKFLOW,
    materialize_workflow_id,
)
from src.materializations.service import MaterializationRunService
from tests.pipeline_factory import build_scenario, make_configuration, make_document

pytestmark = pytest.mark.integration

MATERIALIZATIONS = "/api/v1/materializations"


async def _start(client, *, configuration_id: str, **payload) -> object:
    return await client.post(
        MATERIALIZATIONS,
        json={"chunking_configuration_id": configuration_id, **payload},
    )


# --------------------------------------------------------------------------------------
# 4.3 launching
# --------------------------------------------------------------------------------------


async def test_launching_over_a_corpus_returns_a_run_and_starts_one_workflow(
    client, session, fake_workflows
) -> None:
    """Acceptance of 4.3: one call, a run to poll, and the workflow that will do the work."""
    scenario = await build_scenario(session, missing=3)

    response = await _start(
        client, configuration_id=scenario.configuration_id, corpus_id=scenario.corpus_id
    )

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["started"] is True
    assert body["status"] == "running"
    assert body["document_count"] == 3
    assert body["progress"]["pending"] == 3
    assert body["corpus_id"] == scenario.corpus_id

    assert len(fake_workflows.started) == 1
    call = fake_workflows.started[0]
    assert call.workflow == MATERIALIZE_CHUNKS_WORKFLOW
    assert call.task_queue == CHUNKING_TASK_QUEUE
    assert call.workflow_id == body["workflow_id"]
    assert sorted(call.arg["document_ids"]) == sorted(
        str(document.id) for document in scenario.documents
    )


async def test_the_workflow_id_is_derived_from_the_configuration_and_the_document_set(
    client, session, fake_workflows
) -> None:
    """The id must be reproducible outside the API, or idempotency is only a coincidence."""
    scenario = await build_scenario(session, missing=2)
    document_ids = [document.id for document in scenario.documents]

    body = (
        await _start(
            client,
            configuration_id=scenario.configuration_id,
            document_ids=[str(document_id) for document_id in document_ids],
        )
    ).json()

    assert body["workflow_id"] == materialize_workflow_id(
        scenario.configuration.id, document_ids
    )


async def test_launching_the_same_work_twice_yields_one_run_and_one_workflow(
    client, session, fake_workflows
) -> None:
    """A double click is not a user error (RT-O01): the second call reports the first run."""
    scenario = await build_scenario(session, missing=2)

    first = await _start(
        client, configuration_id=scenario.configuration_id, corpus_id=scenario.corpus_id
    )
    second = await _start(
        client, configuration_id=scenario.configuration_id, corpus_id=scenario.corpus_id
    )

    assert (first.status_code, second.status_code) == (202, 202)
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["started"] is True
    assert second.json()["started"] is False
    assert second.json()["detail"]

    listing = await client.get(MATERIALIZATIONS)
    assert listing.json()["total"] == 1


async def test_the_document_order_does_not_change_the_workflow_id(
    client, session, fake_workflows
) -> None:
    """The identity is the *set* of documents, so listing them backwards is the same request."""
    scenario = await build_scenario(session, missing=3)
    ids = [str(document.id) for document in scenario.documents]

    first = await _start(
        client, configuration_id=scenario.configuration_id, document_ids=ids
    )
    second = await _start(
        client,
        configuration_id=scenario.configuration_id,
        document_ids=list(reversed(ids)),
    )

    assert first.json()["workflow_id"] == second.json()["workflow_id"]
    assert second.json()["started"] is False


async def test_a_repeated_document_is_materialised_once(
    client, session, fake_workflows
) -> None:
    scenario = await build_scenario(session, missing=1)
    document_id = str(scenario.documents[0].id)

    body = (
        await _start(
            client,
            configuration_id=scenario.configuration_id,
            document_ids=[document_id, document_id],
        )
    ).json()

    assert body["document_count"] == 1
    assert fake_workflows.started[0].arg["document_ids"] == [document_id]


async def test_a_different_document_set_is_a_different_run(
    client, session, fake_workflows
) -> None:
    scenario = await build_scenario(session, missing=2)
    ids = [str(document.id) for document in scenario.documents]

    first = await _start(
        client, configuration_id=scenario.configuration_id, document_ids=ids
    )
    second = await _start(
        client, configuration_id=scenario.configuration_id, document_ids=ids[:1]
    )

    assert first.json()["id"] != second.json()["id"]
    assert second.json()["started"] is True
    assert len(fake_workflows.started) == 2


async def test_concurrency_is_forwarded_to_the_workflow(
    client, session, fake_workflows
) -> None:
    scenario = await build_scenario(session, missing=1)

    await _start(
        client,
        configuration_id=scenario.configuration_id,
        corpus_id=scenario.corpus_id,
        concurrency=3,
    )

    assert fake_workflows.started[0].arg["max_concurrency"] == 3


async def test_launching_with_neither_documents_nor_corpus_is_a_422(
    client, session
) -> None:
    _, configuration = await make_configuration(session)

    response = await _start(client, configuration_id=str(configuration.id))

    assert response.status_code == 422
    assert response.json()["code"] == "empty_materialization"


async def test_launching_over_an_empty_corpus_is_a_422(client, session) -> None:
    """Nothing to do is a mistake worth naming, not a run that finishes instantly."""
    scenario = await build_scenario(session)

    response = await _start(
        client, configuration_id=scenario.configuration_id, corpus_id=scenario.corpus_id
    )

    assert response.status_code == 422
    assert response.json()["code"] == "empty_materialization"


async def test_a_document_still_being_fetched_is_refused_with_its_status(
    client, session, fake_workflows
) -> None:
    """Hashing an incomplete upload would key the artefact on a hash that is not final."""
    _, configuration = await make_configuration(session)
    pending = Document(
        content_hash=uuid.uuid4().hex,
        filename="incomplete.pdf",
        mime_type="application/pdf",
        size_bytes=1,
        storage_uri="s3://test-bucket/documents/x/incomplete.pdf",
        status=DocumentStatus.PENDING,
    )
    session.add(pending)
    await session.flush()

    response = await _start(
        client, configuration_id=str(configuration.id), document_ids=[str(pending.id)]
    )

    assert response.status_code == 422
    assert response.json()["code"] == "documents_not_stored"
    assert response.json()["details"]["documents"][str(pending.id)] == "pending"
    assert fake_workflows.started == []


async def test_an_unknown_document_is_refused_before_anything_is_launched(
    client, session, fake_workflows
) -> None:
    _, configuration = await make_configuration(session)
    unknown = uuid.uuid4()

    response = await _start(
        client, configuration_id=str(configuration.id), document_ids=[str(unknown)]
    )

    assert response.status_code == 422
    assert response.json()["details"]["documents"][str(unknown)] == "unknown"
    assert fake_workflows.started == []


async def test_an_unknown_configuration_is_a_404(client, session) -> None:
    document = await make_document(session)

    response = await _start(
        client, configuration_id=str(uuid.uuid4()), document_ids=[str(document.id)]
    )

    assert response.status_code == 404
    assert response.json()["code"] == "chunking_configuration_not_found"


async def test_an_unknown_corpus_is_a_404(client, session) -> None:
    _, configuration = await make_configuration(session)

    response = await _start(
        client, configuration_id=str(configuration.id), corpus_id=str(uuid.uuid4())
    )

    assert response.status_code == 404
    assert response.json()["code"] == "corpus_not_found"


# --------------------------------------------------------------------------------------
# inspecting a run
# --------------------------------------------------------------------------------------


async def test_progress_is_served_from_the_run_row_without_touching_temporal(
    client, session, fake_workflows
) -> None:
    """The UI polls this every couple of seconds (RT-U05), so it must not ask Temporal."""
    scenario = await build_scenario(session, missing=4)
    run_id = (
        await _start(
            client,
            configuration_id=scenario.configuration_id,
            corpus_id=scenario.corpus_id,
        )
    ).json()["id"]
    workflow_id = fake_workflows.started[0].workflow_id
    await MaterializationRunService(session).update_progress(
        workflow_id=workflow_id, progress={"ready": 2, "cached": 1}
    )

    response = await client.get(f"{MATERIALIZATIONS}/{run_id}")

    assert response.status_code == 200
    progress = response.json()["progress"]
    assert (progress["ready"], progress["cached"], progress["pending"]) == (2, 1, 1)
    assert response.json()["status"] == "running"


async def test_a_finished_run_reports_the_reason_of_every_failed_document(
    client, session, fake_workflows
) -> None:
    """Per-document outcomes live on the artefact; the detail view gathers them for the run."""
    scenario = await build_scenario(session, ready=1, failed=1)
    run_id = (
        await _start(
            client,
            configuration_id=scenario.configuration_id,
            corpus_id=scenario.corpus_id,
        )
    ).json()["id"]
    await MaterializationRunService(session).complete_run(
        workflow_id=fake_workflows.started[0].workflow_id,
        progress={"ready": 1, "failed": 1},
    )

    body = (await client.get(f"{MATERIALIZATIONS}/{run_id}")).json()

    assert body["status"] == "failed"
    assert body["finished_at"] is not None
    assert body["failures"] == [
        {"document_id": str(scenario.failed[0].id), "error": "boom"}
    ]


async def test_a_fully_successful_run_is_ready_and_has_no_failures(
    client, session, fake_workflows
) -> None:
    scenario = await build_scenario(session, ready=2)
    run_id = (
        await _start(
            client,
            configuration_id=scenario.configuration_id,
            corpus_id=scenario.corpus_id,
        )
    ).json()["id"]
    await MaterializationRunService(session).complete_run(
        workflow_id=fake_workflows.started[0].workflow_id, progress={"ready": 2}
    )

    body = (await client.get(f"{MATERIALIZATIONS}/{run_id}")).json()

    assert body["status"] == "ready"
    assert body["failures"] == []


async def test_history_lists_every_run_and_filters_by_corpus(
    client, session, fake_workflows
) -> None:
    first = await build_scenario(session, missing=1)
    second = await build_scenario(session, missing=1)
    for scenario in (first, second):
        await _start(
            client,
            configuration_id=scenario.configuration_id,
            corpus_id=scenario.corpus_id,
        )

    everything = (await client.get(MATERIALIZATIONS)).json()
    filtered = (
        await client.get(MATERIALIZATIONS, params={"corpus_id": second.corpus_id})
    ).json()

    assert everything["total"] == 2
    assert {item["corpus_id"] for item in everything["items"]} == {
        first.corpus_id,
        second.corpus_id,
    }
    assert filtered["total"] == 1
    assert filtered["items"][0]["corpus_id"] == second.corpus_id


async def test_history_is_newest_first(client, session, fake_workflows) -> None:
    """The UI opens on the run the user just launched, so order is part of the contract."""
    older = await build_scenario(session, missing=1)
    newer = await build_scenario(session, missing=1)
    for scenario in (older, newer):
        await _start(
            client,
            configuration_id=scenario.configuration_id,
            corpus_id=scenario.corpus_id,
        )
    # `created_at` defaults to `now()`, which is the transaction timestamp and therefore
    # identical for both rows here; a real run per request gets distinct ones.
    runs = MaterializationRunService(session).runs
    stale = await runs.get_by_workflow_id(fake_workflows.started[0].workflow_id)
    assert stale is not None
    stale.created_at = stale.created_at - dt.timedelta(minutes=5)
    await session.flush()

    items = (await client.get(MATERIALIZATIONS)).json()["items"]

    assert [item["corpus_id"] for item in items] == [newer.corpus_id, older.corpus_id]


async def test_history_can_be_paginated(client, session, fake_workflows) -> None:
    scenario = await build_scenario(session, missing=3)
    for document in scenario.documents:
        await _start(
            client,
            configuration_id=scenario.configuration_id,
            document_ids=[str(document.id)],
        )

    page = (await client.get(MATERIALIZATIONS, params={"limit": 2})).json()
    rest = (await client.get(MATERIALIZATIONS, params={"limit": 2, "offset": 2})).json()

    assert page["total"] == rest["total"] == 3
    assert len(page["items"]) == 2
    assert len(rest["items"]) == 1
    ids = {item["id"] for item in page["items"]} | {
        item["id"] for item in rest["items"]
    }
    assert len(ids) == 3


async def test_an_unknown_run_is_a_404(client) -> None:
    response = await client.get(f"{MATERIALIZATIONS}/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["code"] == "materialization_run_not_found"


# --------------------------------------------------------------------------------------
# cancellation
# --------------------------------------------------------------------------------------


async def test_cancelling_a_running_materialisation_stops_the_workflow_and_records_why(
    client, session, fake_workflows
) -> None:
    scenario = await build_scenario(session, missing=2)
    run_id = (
        await _start(
            client,
            configuration_id=scenario.configuration_id,
            corpus_id=scenario.corpus_id,
        )
    ).json()["id"]

    response = await client.post(f"{MATERIALIZATIONS}/{run_id}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["error"] == "cancelled"
    assert response.json()["finished_at"] is not None
    assert fake_workflows.cancelled == [fake_workflows.started[0].workflow_id]


async def test_cancelling_a_finished_run_is_refused(
    client, session, fake_workflows
) -> None:
    """Cancelling something already done would rewrite a terminal state into a lie."""
    scenario = await build_scenario(session, ready=1)
    run_id = (
        await _start(
            client,
            configuration_id=scenario.configuration_id,
            corpus_id=scenario.corpus_id,
        )
    ).json()["id"]
    await MaterializationRunService(session).complete_run(
        workflow_id=fake_workflows.started[0].workflow_id, progress={"ready": 1}
    )

    response = await client.post(f"{MATERIALIZATIONS}/{run_id}/cancel")

    assert response.status_code == 409
    assert response.json()["code"] == "materialization_not_cancellable"
    assert fake_workflows.cancelled == []


async def test_relaunching_after_a_cancellation_starts_a_new_workflow(
    client, session, fake_workflows
) -> None:
    """The id is the same, so the cancelled one must be gone or the relaunch is refused."""
    scenario = await build_scenario(session, missing=2)
    first = (
        await _start(
            client,
            configuration_id=scenario.configuration_id,
            corpus_id=scenario.corpus_id,
        )
    ).json()
    await client.post(f"{MATERIALIZATIONS}/{first['id']}/cancel")

    second = await _start(
        client, configuration_id=scenario.configuration_id, corpus_id=scenario.corpus_id
    )

    assert second.status_code == 202
    assert second.json()["started"] is True
    assert second.json()["id"] == first["id"]
    assert second.json()["status"] == "running"
    assert second.json()["error"] is None


async def test_cancelling_an_unknown_run_is_a_404(client) -> None:
    response = await client.post(f"{MATERIALIZATIONS}/{uuid.uuid4()}/cancel")

    assert response.status_code == 404
    assert response.json()["code"] == "materialization_run_not_found"


async def test_a_cached_document_does_not_stop_a_relaunch(
    client, session, fake_workflows
) -> None:
    """Re-running an already materialised corpus is how the user adds new files to it."""
    scenario = await build_scenario(session, ready=2, missing=1)

    response = await _start(
        client, configuration_id=scenario.configuration_id, corpus_id=scenario.corpus_id
    )

    assert response.status_code == 202
    assert response.json()["document_count"] == 3
    assert ArtifactStatus(response.json()["status"]) is ArtifactStatus.RUNNING
