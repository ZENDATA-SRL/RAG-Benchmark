from __future__ import annotations

import uuid

import pytest
from src.corpora.service import CorpusService, CorpusSnapshotService

pytestmark = pytest.mark.integration

CORPORA_URL = "/api/v1/corpora"
DOCUMENTS_URL = "/api/v1/documents"
PDF = "application/pdf"
UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"


async def _corpus_with_documents(client, count: int = 2) -> tuple[str, list[str]]:
    """Create a corpus holding `count` freshly uploaded documents."""
    corpus_id = (await client.post(CORPORA_URL, json={"name": "Base"})).json()["id"]
    upload = await client.post(
        f"{CORPORA_URL}/{corpus_id}/documents/upload",
        files=[
            ("files", (f"d{index}.pdf", f"%PDF-1.4 {index}".encode(), PDF))
            for index in range(count)
        ],
    )
    document_ids = [result["document_id"] for result in upload.json()["results"]]
    return corpus_id, document_ids


async def test_a_corpus_is_created_and_read_back(client) -> None:
    """The create/read round trip exposes no ORM object and no internal column."""
    created = await client.post(
        CORPORA_URL, json={"name": "Normativa", "description": "Testi di legge"}
    )

    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "Normativa"

    fetched = await client.get(f"{CORPORA_URL}/{body['id']}")
    assert fetched.status_code == 200
    assert set(fetched.json()) == {
        "id",
        "name",
        "description",
        "created_at",
        "updated_at",
    }


async def test_corpora_are_listed_as_a_page(client) -> None:
    """The listing carries the total, which is what lets the UI render a pager."""
    await client.post(CORPORA_URL, json={"name": "Alfa"})
    await client.post(CORPORA_URL, json={"name": "Beta"})

    response = await client.get(CORPORA_URL, params={"limit": 1, "offset": 0})

    body = response.json()
    assert body["total"] == 2
    assert len(body["items"]) == 1
    assert body["limit"] == 1
    assert body["offset"] == 0


async def test_a_corpus_can_be_renamed(client) -> None:
    """An omitted field is left unchanged rather than blanked."""
    corpus_id = (
        await client.post(CORPORA_URL, json={"name": "Vecchio", "description": "resta"})
    ).json()["id"]

    response = await client.patch(f"{CORPORA_URL}/{corpus_id}", json={"name": "Nuovo"})

    assert response.json()["name"] == "Nuovo"
    assert response.json()["description"] == "resta"


async def test_existing_documents_can_be_added_to_a_corpus(client) -> None:
    """Documents already in the platform are filed without being uploaded again."""
    upload = await client.post(
        f"{DOCUMENTS_URL}/upload",
        files=[("files", ("libero.pdf", b"%PDF-1.4 libero", PDF))],
    )
    document_id = upload.json()["results"][0]["document_id"]
    corpus_id = (await client.post(CORPORA_URL, json={"name": "Raccolta"})).json()["id"]

    response = await client.post(
        f"{CORPORA_URL}/{corpus_id}/documents", json={"document_ids": [document_id]}
    )

    assert response.status_code == 200
    assert response.json()["document_count"] == 1


async def test_adding_the_same_document_twice_does_not_duplicate_membership(client) -> None:
    """Membership is a set: re-adding is a no-op and not an error."""
    corpus_id, document_ids = await _corpus_with_documents(client, count=1)

    response = await client.post(
        f"{CORPORA_URL}/{corpus_id}/documents", json={"document_ids": document_ids}
    )

    assert response.json()["document_count"] == 1


async def test_adding_an_unknown_document_is_rejected(client) -> None:
    """A wrong id is refused instead of silently adding nothing."""
    corpus_id = (await client.post(CORPORA_URL, json={"name": "Vuoto"})).json()["id"]

    response = await client.post(
        f"{CORPORA_URL}/{corpus_id}/documents", json={"document_ids": [UNKNOWN_ID]}
    )

    assert response.status_code == 422
    assert response.json()["code"] == "unknown_documents"


async def test_removing_a_document_keeps_the_document_and_its_snapshots(
    client, session
) -> None:
    """A removal from a corpus touches neither the document nor a frozen snapshot (RF-C05)."""
    corpus_id, document_ids = await _corpus_with_documents(client, count=2)

    snapshots = CorpusSnapshotService(session)
    snapshot = await snapshots.get_or_create(
        uuid.UUID(corpus_id),
        [uuid.UUID(doc_id) for doc_id in document_ids],
        label="prima della rimozione",
    )
    await session.flush()
    frozen_before = await snapshots.snapshots.count_snapshot_documents(snapshot.id)

    response = await client.delete(f"{CORPORA_URL}/{corpus_id}/documents/{document_ids[0]}")

    assert response.status_code == 200
    assert response.json()["snapshots_unaffected"] is True

    # The document still exists on its own.
    assert (await client.get(f"{DOCUMENTS_URL}/{document_ids[0]}")).status_code == 200
    # The corpus lost the membership.
    listed = await client.get(f"{CORPORA_URL}/{corpus_id}/documents")
    assert listed.json()["total"] == 1
    # The snapshot kept its whole composition.
    frozen_after = await snapshots.snapshots.count_snapshot_documents(snapshot.id)
    assert frozen_after == frozen_before == 2


async def test_a_corpus_with_snapshots_cannot_be_deleted(client, session) -> None:
    """Deleting would cascade the snapshots away and with them past measurements (RF-C05)."""
    corpus_id, document_ids = await _corpus_with_documents(client, count=1)

    await CorpusSnapshotService(session).get_or_create(
        uuid.UUID(corpus_id),
        [uuid.UUID(document_ids[0])],
        label="congelato",
    )
    await session.flush()

    response = await client.delete(f"{CORPORA_URL}/{corpus_id}")

    assert response.status_code == 409
    assert response.json()["code"] == "corpus_has_snapshots"
    assert (await client.get(f"{CORPORA_URL}/{corpus_id}")).status_code == 200


async def test_a_corpus_without_snapshots_is_deleted(client) -> None:
    """Nothing was ever measured on it, so it can go."""
    corpus_id = (await client.post(CORPORA_URL, json={"name": "Usa e getta"})).json()["id"]

    response = await client.delete(f"{CORPORA_URL}/{corpus_id}")

    assert response.status_code == 204
    assert (await client.get(f"{CORPORA_URL}/{corpus_id}")).status_code == 404


async def test_corpus_progress_reports_every_status(client) -> None:
    """Every status is present, zero included, so the UI renders a stable set of bars (RF-C04)."""
    corpus_id, _ = await _corpus_with_documents(client, count=2)

    response = await client.get(f"{CORPORA_URL}/{corpus_id}/progress")

    body = response.json()
    assert body["total"] == 2
    assert body["by_status"] == {
        "pending": 0,
        "fetching": 0,
        "stored": 2,
        "failed": 0,
    }


async def test_corpus_documents_can_be_filtered_by_status(client) -> None:
    """The status filter is applied to the window and to its total."""
    corpus_id, _ = await _corpus_with_documents(client, count=2)

    stored = await client.get(
        f"{CORPORA_URL}/{corpus_id}/documents", params={"status": "stored"}
    )
    failed = await client.get(
        f"{CORPORA_URL}/{corpus_id}/documents", params={"status": "failed"}
    )

    assert stored.json()["total"] == 2
    assert failed.json()["total"] == 0


async def test_listing_the_documents_of_an_unknown_corpus_is_a_404(client) -> None:
    """An unknown id is a 404, not an empty corpus."""
    response = await client.get(f"{CORPORA_URL}/{UNKNOWN_ID}/documents")

    assert response.status_code == 404
    assert response.json()["code"] == "corpus_not_found"


async def test_progress_of_an_empty_corpus_is_all_zeros(client, session) -> None:
    """An empty corpus is a valid state and must not be an error."""
    corpus = await CorpusService(session).create("Appena nato")
    await session.flush()

    response = await client.get(f"{CORPORA_URL}/{corpus.id}/progress")

    assert response.status_code == 200
    assert response.json()["total"] == 0
