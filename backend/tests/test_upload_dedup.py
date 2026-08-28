from __future__ import annotations

import hashlib
import io

import pytest
from src.documents.service import DocumentService, UploadCandidate
from src.infrastructure.database.enums import DocumentStatus, FileOutcome, ImportStatus
from src.infrastructure.storage import document_key
from src.sources.service import UploadImportService

pytestmark = pytest.mark.integration

PDF = "application/pdf"


async def _connection_id(session) -> object:
    selection = await UploadImportService(session).get_or_create_selection()
    return selection.connection_id


def _pdf(body: bytes = b"%PDF-1.4 first") -> io.BytesIO:
    return io.BytesIO(body)


async def test_same_content_under_two_names_is_one_document_with_two_provenances(
    session, fake_storage, settings
) -> None:
    """Identity is the content: two names for the same bytes are one document (RF-S06)."""
    service = DocumentService(session, fake_storage, settings)
    connection_id = await _connection_id(session)

    first, first_duplicate = await service.ingest_upload(
        _pdf(), filename="report.pdf", content_type=PDF, connection_id=connection_id
    )
    second, second_duplicate = await service.ingest_upload(
        _pdf(), filename="copia-report.pdf", content_type=PDF, connection_id=connection_id
    )

    assert first_duplicate is False
    assert second_duplicate is True
    assert second.id == first.id

    provenances = await service.list_provenances(first.id)
    assert {provenance.original_uri for provenance in provenances} == {
        "report.pdf",
        "copia-report.pdf",
    }


async def test_a_duplicate_does_not_rewrite_the_object(
    session, fake_storage, settings
) -> None:
    """A known content is not uploaded again: the key derives from the bytes."""
    service = DocumentService(session, fake_storage, settings)
    connection_id = await _connection_id(session)

    await service.ingest_upload(
        _pdf(), filename="a.pdf", content_type=PDF, connection_id=connection_id
    )
    await service.ingest_upload(
        _pdf(), filename="b.pdf", content_type=PDF, connection_id=connection_id
    )

    assert len(fake_storage.put_calls) == 1


async def test_different_content_under_the_same_name_is_two_documents(
    session, fake_storage, settings
) -> None:
    """The filename is not an identity: same name, different bytes, two documents."""
    service = DocumentService(session, fake_storage, settings)
    connection_id = await _connection_id(session)

    first, _ = await service.ingest_upload(
        _pdf(b"%PDF-1.4 one"),
        filename="same.pdf",
        content_type=PDF,
        connection_id=connection_id,
    )
    second, was_duplicate = await service.ingest_upload(
        _pdf(b"%PDF-1.4 two"),
        filename="same.pdf",
        content_type=PDF,
        connection_id=connection_id,
    )

    assert was_duplicate is False
    assert second.id != first.id


async def test_a_stored_document_is_readable_and_content_addressed(
    session, fake_storage, settings
) -> None:
    """The stored bytes are the uploaded bytes, under the key derived from their hash."""
    service = DocumentService(session, fake_storage, settings)
    connection_id = await _connection_id(session)
    body = b"%PDF-1.4 payload"

    document, _ = await service.ingest_upload(
        _pdf(body), filename="doc.pdf", content_type=PDF, connection_id=connection_id
    )

    assert document.status is DocumentStatus.STORED
    assert document.size_bytes == len(body)
    key = document_key(document.content_hash, document.filename)
    assert fake_storage.objects[key] == body
    assert document.storage_uri.endswith(key)


async def test_an_unsupported_mime_type_does_not_stop_the_batch(
    session, fake_storage, settings
) -> None:
    """A rejected file is reported and the others still make it (RF-S11)."""
    service = DocumentService(session, fake_storage, settings)
    connection_id = await _connection_id(session)

    outcomes = await service.ingest_upload_batch(
        [
            UploadCandidate("a.pdf", PDF, _pdf(b"%PDF-1.4 a")),
            UploadCandidate("notes.txt", "text/plain", io.BytesIO(b"plain text")),
            UploadCandidate("b.pdf", PDF, _pdf(b"%PDF-1.4 b")),
        ],
        connection_id=connection_id,
    )

    assert [outcome.outcome for outcome in outcomes] == [
        FileOutcome.IMPORTED,
        FileOutcome.SKIPPED_UNSUPPORTED,
        FileOutcome.IMPORTED,
    ]
    assert outcomes[1].document_id is None
    assert outcomes[1].error_reason is not None


async def test_a_storage_failure_marks_the_document_failed_without_stopping_the_batch(
    session, fake_storage, settings
) -> None:
    """A backend refusal leaves `failed` with the reason and spares the rest (RF-C04)."""
    service = DocumentService(session, fake_storage, settings)
    connection_id = await _connection_id(session)

    broken = b"%PDF-1.4 broken"
    broken_key = document_key(hashlib.sha256(broken).hexdigest(), "broken.pdf")
    fake_storage.fail_on_keys.add(broken_key)

    outcomes = await service.ingest_upload_batch(
        [
            UploadCandidate("broken.pdf", PDF, io.BytesIO(broken)),
            UploadCandidate("fine.pdf", PDF, _pdf(b"%PDF-1.4 fine")),
        ],
        connection_id=connection_id,
    )

    assert outcomes[0].outcome is FileOutcome.FAILED
    assert outcomes[1].outcome is FileOutcome.IMPORTED

    failed = await service.get(outcomes[0].document_id)
    assert failed.status is DocumentStatus.FAILED
    assert failed.error


async def test_an_empty_file_is_rejected(session, fake_storage, settings) -> None:
    """Every empty file shares one hash, so accepting them would merge unrelated uploads."""
    service = DocumentService(session, fake_storage, settings)
    connection_id = await _connection_id(session)

    outcomes = await service.ingest_upload_batch(
        [UploadCandidate("empty.pdf", PDF, io.BytesIO(b""))],
        connection_id=connection_id,
    )

    assert outcomes[0].outcome is FileOutcome.FAILED


async def test_a_file_over_the_limit_is_rejected(session, fake_storage, settings) -> None:
    """The limit is enforced while reading, not after the whole file is buffered."""
    tiny = settings.model_copy(update={"max_upload_bytes": 8})
    service = DocumentService(session, fake_storage, tiny)
    connection_id = await _connection_id(session)

    outcomes = await service.ingest_upload_batch(
        [UploadCandidate("big.pdf", PDF, io.BytesIO(b"%PDF-1.4 " + b"x" * 100))],
        connection_id=connection_id,
    )

    assert outcomes[0].outcome is FileOutcome.FAILED
    assert "too large" in (outcomes[0].error_reason or "")
    assert fake_storage.put_calls == []


async def test_an_import_run_of_three_files_is_succeeded_with_its_counts(
    session, fake_storage, settings
) -> None:
    """Three good files produce `counts = {imported: 3}` and status `succeeded`."""
    imports = UploadImportService(session)
    documents = DocumentService(session, fake_storage, settings)
    run = await imports.open_run()
    connection_id = await _connection_id(session)

    outcomes = await documents.ingest_upload_batch(
        [
            UploadCandidate(f"f{index}.pdf", PDF, _pdf(f"%PDF-1.4 {index}".encode()))
            for index in range(3)
        ],
        connection_id=connection_id,
    )
    for outcome in outcomes:
        imports.record_file_result(
            run,
            source_uri=outcome.filename,
            outcome=outcome.outcome,
            document_id=outcome.document_id,
        )
    await imports.close_run(run)

    assert run.counts == {FileOutcome.IMPORTED.value: 3}
    assert run.status is ImportStatus.SUCCEEDED
    assert run.finished_at is not None


async def test_a_batch_with_one_rejected_file_closes_as_partial(
    session, fake_storage, settings
) -> None:
    """A mixed batch is `partial`: the imported documents exist and must not invite a retry."""
    imports = UploadImportService(session)
    documents = DocumentService(session, fake_storage, settings)
    run = await imports.open_run()
    connection_id = await _connection_id(session)

    outcomes = await documents.ingest_upload_batch(
        [
            UploadCandidate("ok.pdf", PDF, _pdf()),
            UploadCandidate("no.txt", "text/plain", io.BytesIO(b"nope")),
        ],
        connection_id=connection_id,
    )
    for outcome in outcomes:
        imports.record_file_result(
            run,
            source_uri=outcome.filename,
            outcome=outcome.outcome,
            document_id=outcome.document_id,
            error_reason=outcome.error_reason,
        )
    await imports.close_run(run)

    assert run.status is ImportStatus.PARTIAL
    assert run.counts == {
        FileOutcome.IMPORTED.value: 1,
        FileOutcome.SKIPPED_UNSUPPORTED.value: 1,
    }


async def test_the_upload_source_seed_is_idempotent(session) -> None:
    """Two boots reuse the same connection, so provenances keep pointing at one row."""
    service = UploadImportService(session)

    first = await service.get_or_create_selection()
    second = await service.get_or_create_selection()

    assert first.id == second.id
    assert first.connection_id == second.connection_id
