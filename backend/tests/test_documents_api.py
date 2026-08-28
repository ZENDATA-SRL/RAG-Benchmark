from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

DOCUMENTS_URL = "/api/v1/documents"
CORPORA_URL = "/api/v1/corpora"
PDF = "application/pdf"


def _files(*items: tuple[str, bytes, str]) -> list[tuple[str, tuple[str, bytes, str]]]:
    return [("files", (name, body, content_type)) for name, body, content_type in items]


async def test_uploading_three_files_with_one_unsupported_returns_200(client) -> None:
    """A `.txt` in the batch is skipped, the two PDFs are imported, the request is 200 (RF-S11)."""
    response = await client.post(
        f"{DOCUMENTS_URL}/upload",
        files=_files(
            ("a.pdf", b"%PDF-1.4 a", PDF),
            ("notes.txt", b"plain", "text/plain"),
            ("b.pdf", b"%PDF-1.4 b", PDF),
        ),
    )

    assert response.status_code == 200
    body = response.json()
    assert [result["outcome"] for result in body["results"]] == [
        "imported",
        "skipped_unsupported",
        "imported",
    ]
    assert body["counts"] == {"imported": 2, "skipped_unsupported": 1}
    assert body["import_run_id"]


async def test_reuploading_the_same_file_reports_skipped_duplicate(client) -> None:
    """The second upload of the same bytes creates nothing and says so in the summary."""
    first = await client.post(
        f"{DOCUMENTS_URL}/upload", files=_files(("x.pdf", b"%PDF-1.4 x", PDF))
    )
    second = await client.post(
        f"{DOCUMENTS_URL}/upload", files=_files(("altro-nome.pdf", b"%PDF-1.4 x", PDF))
    )

    assert first.json()["results"][0]["outcome"] == "imported"
    assert second.json()["results"][0]["outcome"] == "skipped_duplicate"
    assert second.json()["results"][0]["document_id"] == first.json()["results"][0]["document_id"]

    listed = await client.get(DOCUMENTS_URL)
    assert listed.json()["total"] == 1


async def test_a_document_card_exposes_its_hash_and_provenances(client) -> None:
    """The card carries `content_hash` and every origin, so the UI can reach the original (RT-U06)."""
    upload = await client.post(
        f"{DOCUMENTS_URL}/upload", files=_files(("uno.pdf", b"%PDF-1.4 uno", PDF))
    )
    document_id = upload.json()["results"][0]["document_id"]
    await client.post(
        f"{DOCUMENTS_URL}/upload", files=_files(("due.pdf", b"%PDF-1.4 uno", PDF))
    )

    response = await client.get(f"{DOCUMENTS_URL}/{document_id}")

    assert response.status_code == 200
    body = response.json()
    assert len(body["content_hash"]) == 64
    assert body["status"] == "stored"
    assert {provenance["original_uri"] for provenance in body["provenances"]} == {
        "uno.pdf",
        "due.pdf",
    }


async def test_the_document_content_is_streamed_back_unchanged(client) -> None:
    """The download returns the uploaded bytes, for the native preview of the UI (RT-U04)."""
    body = b"%PDF-1.4 scaricabile"
    upload = await client.post(
        f"{DOCUMENTS_URL}/upload", files=_files(("dl.pdf", body, PDF))
    )
    document_id = upload.json()["results"][0]["document_id"]

    response = await client.get(f"{DOCUMENTS_URL}/{document_id}/content")

    assert response.status_code == 200
    assert response.content == body
    assert response.headers["content-type"].startswith(PDF)


async def test_listing_documents_filters_by_status(client) -> None:
    """The status filter is applied to both the window and its total."""
    await client.post(f"{DOCUMENTS_URL}/upload", files=_files(("s.pdf", b"%PDF-1.4 s", PDF)))

    stored = await client.get(DOCUMENTS_URL, params={"status": "stored"})
    failed = await client.get(DOCUMENTS_URL, params={"status": "failed"})

    assert stored.json()["total"] == 1
    assert failed.json()["total"] == 0
    assert failed.json()["items"] == []


async def test_document_metadata_can_be_replaced(client) -> None:
    """Metadata is a property of the file and becomes a retrieval filter (RF-C02)."""
    upload = await client.post(
        f"{DOCUMENTS_URL}/upload", files=_files(("m.pdf", b"%PDF-1.4 m", PDF))
    )
    document_id = upload.json()["results"][0]["document_id"]

    response = await client.patch(
        f"{DOCUMENTS_URL}/{document_id}/metadata",
        json={"metadata": {"anno": 2026, "reparto": "legale"}},
    )

    assert response.status_code == 200
    assert response.json()["metadata"] == {"anno": 2026, "reparto": "legale"}


async def test_an_unknown_document_is_a_uniform_404(client) -> None:
    """A missing document produces the shared error contract, not a stack trace."""
    response = await client.get(f"{DOCUMENTS_URL}/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    assert set(response.json()) == {"code", "message", "details"}
    assert response.json()["code"] == "document_not_found"


async def test_uploading_into_a_corpus_files_the_documents(client) -> None:
    """The corpus shortcut uploads and files in one act; it is what the UI calls."""
    corpus_id = (
        await client.post(CORPORA_URL, json={"name": "Contratti"})
    ).json()["id"]

    response = await client.post(
        f"{CORPORA_URL}/{corpus_id}/documents/upload",
        files=_files(("c1.pdf", b"%PDF-1.4 c1", PDF), ("c2.pdf", b"%PDF-1.4 c2", PDF)),
    )

    assert response.status_code == 200
    assert response.json()["counts"] == {"imported": 2}

    documents = await client.get(f"{CORPORA_URL}/{corpus_id}/documents")
    assert documents.json()["total"] == 2


async def test_uploading_into_an_unknown_corpus_is_a_404(client) -> None:
    """The corpus is validated before any byte is spooled, so nothing is left orphaned."""
    response = await client.post(
        f"{CORPORA_URL}/00000000-0000-0000-0000-000000000000/documents/upload",
        files=_files(("x.pdf", b"%PDF-1.4 x", PDF)),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "corpus_not_found"
