from __future__ import annotations

import json

import pytest
from sqlalchemy import select
from src.artifacts.models import Chunk, ChunkResult
from src.corpora.models import CorpusDocument
from tests.pipeline_factory import build_scenario, make_document

pytestmark = pytest.mark.integration

QA_SETS = "/api/v1/qa-sets"
QUESTIONS = "/api/v1/questions"


async def _qa_set(client, scenario) -> str:
    response = await client.post(
        QA_SETS, json={"name": "Capitolati QA", "origin_corpus_id": scenario.corpus_id}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _question(client, qa_set_id: str, **body) -> dict:
    payload = {"text": "What is the penalty for late delivery?", **body}
    response = await client.post(f"{QA_SETS}/{qa_set_id}/questions", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def _chunks(session, document, configuration) -> list[Chunk]:
    stmt = (
        select(Chunk)
        .join(ChunkResult, ChunkResult.id == Chunk.chunk_result_id)
        .where(
            ChunkResult.document_id == document.id,
            ChunkResult.chunking_configuration_id == configuration.id,
        )
        .order_by(Chunk.ordinal)
    )
    return list((await session.scalars(stmt)).all())


async def _freeze(client, qa_set_id: str) -> None:
    response = await client.post(f"{QA_SETS}/{qa_set_id}/snapshots", json={})
    assert response.status_code == 201, response.text


# --------------------------------------------------------------------------------------
# Questions
# --------------------------------------------------------------------------------------


async def test_a_question_is_written_with_answers_and_gold(client, session) -> None:
    scenario = await build_scenario(session, ready=1)
    qa_set_id = await _qa_set(client, scenario)
    document = scenario.ready[0]

    created = await _question(
        client,
        qa_set_id,
        tags=["penalty", " penalty ", ""],
        expected_answers=[
            {"text": "1 per mille per day"},
            {"text": "0.1% a day"},
        ],
        gold_document_ids=[str(document.id)],
    )

    assert created["tags"] == ["penalty"]
    assert created["frozen"] is False
    assert created["expected_answers"] == [
        {"text": "1 per mille per day", "is_primary": True},
        {"text": "0.1% a day", "is_primary": False},
    ]
    assert [gold["document_id"] for gold in created["gold_documents"]] == [
        str(document.id)
    ]
    listed = (await client.get(f"{QA_SETS}/{qa_set_id}")).json()
    assert listed["question_count"] == 1


async def test_two_questions_cannot_share_a_text(client, session) -> None:
    scenario = await build_scenario(session, ready=1)
    qa_set_id = await _qa_set(client, scenario)
    await _question(client, qa_set_id)

    response = await client.post(
        f"{QA_SETS}/{qa_set_id}/questions",
        json={"text": "  What is the penalty for late delivery?  "},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "question_already_in_set"


async def test_more_than_one_primary_answer_is_refused(client, session) -> None:
    scenario = await build_scenario(session, ready=1)
    qa_set_id = await _qa_set(client, scenario)

    response = await client.post(
        f"{QA_SETS}/{qa_set_id}/questions",
        json={
            "text": "Q?",
            "expected_answers": [
                {"text": "a", "is_primary": True},
                {"text": "b", "is_primary": True},
            ],
        },
    )

    assert response.status_code == 422


async def test_a_gold_document_outside_the_origin_corpus_is_refused(
    client, session
) -> None:
    scenario = await build_scenario(session, ready=1)
    stranger = await make_document(session, "elsewhere.pdf")
    qa_set_id = await _qa_set(client, scenario)

    response = await client.post(
        f"{QA_SETS}/{qa_set_id}/questions",
        json={"text": "Q?", "gold_document_ids": [str(stranger.id)]},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "documents_not_in_origin_corpus"


async def test_a_question_not_yet_frozen_is_edited_and_deleted(client, session) -> None:
    scenario = await build_scenario(session, ready=1)
    qa_set_id = await _qa_set(client, scenario)
    question = await _question(client, qa_set_id, expected_answers=[{"text": "old"}])

    edited = await client.patch(
        f"{QUESTIONS}/{question['id']}",
        json={"text": "Rephrased?", "answerable": False, "expected_answers": []},
    )
    assert edited.status_code == 200, edited.text
    body = edited.json()
    assert body["text"] == "Rephrased?"
    assert body["answerable"] is False
    assert body["expected_answers"] == []

    deleted = await client.delete(f"{QUESTIONS}/{question['id']}")
    assert deleted.status_code == 204
    assert (await client.get(f"{QUESTIONS}/{question['id']}")).status_code == 404


async def test_a_frozen_question_is_neither_edited_nor_deleted(client, session) -> None:
    scenario = await build_scenario(session, ready=1)
    qa_set_id = await _qa_set(client, scenario)
    question = await _question(client, qa_set_id)
    await _freeze(client, qa_set_id)

    assert (await client.get(f"{QUESTIONS}/{question['id']}")).json()["frozen"] is True
    edited = await client.patch(f"{QUESTIONS}/{question['id']}", json={"text": "New?"})
    deleted = await client.delete(f"{QUESTIONS}/{question['id']}")

    assert edited.status_code == deleted.status_code == 409
    assert edited.json()["code"] == "question_frozen"


async def test_replacing_a_frozen_question_keeps_the_old_snapshot(
    client, session
) -> None:
    scenario = await build_scenario(session, ready=1)
    qa_set_id = await _qa_set(client, scenario)
    question = await _question(client, qa_set_id, tags=["a"])
    other = await _question(client, qa_set_id, text="Another question?")
    first = (await client.post(f"{QA_SETS}/{qa_set_id}/snapshots", json={})).json()[
        "snapshot"
    ]

    replaced = await client.post(
        f"{QUESTIONS}/{question['id']}/replace",
        json={"text": question["text"], "tags": ["b"]},
    )
    assert replaced.status_code == 201, replaced.text
    successor = replaced.json()

    old = (await client.get(f"{QUESTIONS}/{question['id']}")).json()
    assert old["replaced_by_question_id"] == successor["id"]
    listed = (await client.get(f"{QA_SETS}/{qa_set_id}")).json()
    assert {item["id"] for item in listed["questions"]["items"]} == {
        other["id"],
        successor["id"],
    }
    second = (await client.post(f"{QA_SETS}/{qa_set_id}/snapshots", json={})).json()
    assert second["created"] is True
    assert second["snapshot"]["id"] != first["id"]
    assert second["snapshot"]["question_count"] == 2

    again = await client.post(
        f"{QUESTIONS}/{question['id']}/replace", json={"text": "Third?"}
    )
    assert again.status_code == 409
    assert again.json()["code"] == "question_replaced"


async def test_deleting_the_successor_brings_the_replaced_question_back(
    client, session
) -> None:
    scenario = await build_scenario(session, ready=1)
    qa_set_id = await _qa_set(client, scenario)
    question = await _question(client, qa_set_id)
    await _freeze(client, qa_set_id)
    successor = (
        await client.post(
            f"{QUESTIONS}/{question['id']}/replace", json={"text": "Better?"}
        )
    ).json()

    assert (await client.delete(f"{QUESTIONS}/{successor['id']}")).status_code == 204

    session.expire_all()
    listed = (await client.get(f"{QA_SETS}/{qa_set_id}")).json()
    assert [item["id"] for item in listed["questions"]["items"]] == [question["id"]]


# --------------------------------------------------------------------------------------
# Gold documents
# --------------------------------------------------------------------------------------


async def test_gold_documents_are_set_even_on_a_frozen_question(
    client, session
) -> None:
    scenario = await build_scenario(session, ready=2)
    qa_set_id = await _qa_set(client, scenario)
    first, second = scenario.ready
    question = await _question(client, qa_set_id, gold_document_ids=[str(first.id)])
    await _freeze(client, qa_set_id)

    response = await client.put(
        f"{QUESTIONS}/{question['id']}/gold-documents",
        json={"document_ids": [str(second.id)]},
    )

    assert response.status_code == 200, response.text
    assert [g["document_id"] for g in response.json()["gold_documents"]] == [
        str(second.id)
    ]


async def test_a_gold_document_with_confirmed_evidence_cannot_be_removed(
    client, session
) -> None:
    scenario = await build_scenario(session, ready=1)
    qa_set_id = await _qa_set(client, scenario)
    document = scenario.ready[0]
    chunk = (await _chunks(session, document, scenario.configuration))[0]
    question = await _question(client, qa_set_id)
    confirmed = await client.put(
        f"{QUESTIONS}/{question['id']}/evidence",
        json={
            "chunking_configuration_id": scenario.configuration_id,
            "status": "confirmed",
            "annotator": "anna",
            "chunks": [{"chunk_id": str(chunk.id), "relevance": "sufficient"}],
        },
    )
    assert confirmed.status_code == 200, confirmed.text

    response = await client.put(
        f"{QUESTIONS}/{question['id']}/gold-documents", json={"document_ids": []}
    )

    assert response.status_code == 409
    assert response.json()["details"]["document_ids"] == [str(document.id)]


# --------------------------------------------------------------------------------------
# Evidence
# --------------------------------------------------------------------------------------


async def test_evidence_is_not_reviewed_until_a_link_exists(client, session) -> None:
    scenario = await build_scenario(session, ready=1)
    qa_set_id = await _qa_set(client, scenario)
    question = await _question(client, qa_set_id)

    response = await client.get(
        f"{QUESTIONS}/{question['id']}/evidence",
        params={"chunking_configuration_id": scenario.configuration_id},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "not_reviewed"
    assert response.json()["chunks"] == []


async def test_confirming_chunks_records_them_and_derives_gold_documents(
    client, session
) -> None:
    scenario = await build_scenario(session, ready=2, chunks_per_document=3)
    qa_set_id = await _qa_set(client, scenario)
    first, second = scenario.ready
    first_chunks = await _chunks(session, first, scenario.configuration)
    second_chunks = await _chunks(session, second, scenario.configuration)
    question = await _question(client, qa_set_id, gold_document_ids=[str(first.id)])

    response = await client.put(
        f"{QUESTIONS}/{question['id']}/evidence",
        json={
            "chunking_configuration_id": scenario.configuration_id,
            "status": "confirmed",
            "annotator": "anna",
            "chunks": [
                {"chunk_id": str(first_chunks[1].id), "relevance": "sufficient"},
                {
                    "chunk_id": str(second_chunks[0].id),
                    "relevance": "supporting",
                    "graded_relevance": 1,
                },
            ],
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "confirmed"
    assert body["confirmed_by"] == "anna"
    assert body["confirmed_at"] is not None
    assert body["added_gold_document_ids"] == [str(second.id)]
    assert [(c["filename"], c["ordinal"], c["relevance"]) for c in body["chunks"]] == [
        (first.filename, 1, "sufficient"),
        (second.filename, 0, "supporting"),
    ]
    detail = (await client.get(f"{QUESTIONS}/{question['id']}")).json()
    assert {g["document_id"] for g in detail["gold_documents"]} == {
        str(first.id),
        str(second.id),
    }


async def test_saving_evidence_again_replaces_it(client, session) -> None:
    scenario = await build_scenario(session, ready=1, chunks_per_document=2)
    qa_set_id = await _qa_set(client, scenario)
    chunks = await _chunks(session, scenario.ready[0], scenario.configuration)
    question = await _question(client, qa_set_id)
    url = f"{QUESTIONS}/{question['id']}/evidence"
    base = {"chunking_configuration_id": scenario.configuration_id}

    draft = await client.put(
        url,
        json={
            **base,
            "status": "to_review",
            "chunks": [{"chunk_id": str(chunks[0].id), "relevance": "supporting"}],
        },
    )
    assert draft.json()["status"] == "to_review"
    assert draft.json()["confirmed_by"] is None
    assert draft.json()["added_gold_document_ids"] == []

    final = await client.put(
        url,
        json={
            **base,
            "status": "confirmed",
            "annotator": "bruno",
            "chunks": [{"chunk_id": str(chunks[1].id), "relevance": "sufficient"}],
        },
    )
    assert [c["chunk_id"] for c in final.json()["chunks"]] == [str(chunks[1].id)]

    not_found = await client.put(
        url, json={**base, "status": "not_found", "annotator": "bruno"}
    )
    assert not_found.status_code == 200, not_found.text
    assert not_found.json()["status"] == "not_found"
    assert not_found.json()["chunks"] == []


@pytest.mark.parametrize(
    ("status", "with_chunk", "annotator", "reason"),
    [
        ("confirmed", False, "anna", "chunks_required"),
        ("not_found", True, "anna", "chunks_not_allowed"),
        ("confirmed", True, "  ", "annotator_required"),
        ("not_found", False, None, "annotator_required"),
    ],
)
async def test_evidence_status_rules(
    client, session, status, with_chunk, annotator, reason
) -> None:
    scenario = await build_scenario(session, ready=1)
    qa_set_id = await _qa_set(client, scenario)
    chunk = (await _chunks(session, scenario.ready[0], scenario.configuration))[0]
    question = await _question(client, qa_set_id)

    response = await client.put(
        f"{QUESTIONS}/{question['id']}/evidence",
        json={
            "chunking_configuration_id": scenario.configuration_id,
            "status": status,
            "annotator": annotator,
            "chunks": (
                [{"chunk_id": str(chunk.id), "relevance": "sufficient"}]
                if with_chunk
                else []
            ),
        },
    )

    assert response.status_code == 422
    assert response.json()["details"]["reason"] == reason


async def test_a_question_not_answerable_has_no_evidence(client, session) -> None:
    scenario = await build_scenario(session, ready=1)
    qa_set_id = await _qa_set(client, scenario)
    question = await _question(client, qa_set_id, answerable=False)

    response = await client.put(
        f"{QUESTIONS}/{question['id']}/evidence",
        json={
            "chunking_configuration_id": scenario.configuration_id,
            "status": "not_found",
            "annotator": "anna",
        },
    )

    assert response.status_code == 422
    assert response.json()["details"]["reason"] == "question_not_answerable"


async def test_a_chunk_of_another_configuration_is_refused(client, session) -> None:
    scenario = await build_scenario(session, ready=1)
    other = await build_scenario(session, ready=1, chunk_size=900)
    qa_set_id = await _qa_set(client, scenario)
    foreign = (await _chunks(session, other.ready[0], other.configuration))[0]
    question = await _question(client, qa_set_id)

    response = await client.put(
        f"{QUESTIONS}/{question['id']}/evidence",
        json={
            "chunking_configuration_id": scenario.configuration_id,
            "status": "confirmed",
            "annotator": "anna",
            "chunks": [{"chunk_id": str(foreign.id), "relevance": "sufficient"}],
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "evidence_chunks_outside_configuration"


async def test_a_chunk_of_a_document_outside_the_corpus_is_refused(
    client, session
) -> None:
    scenario = await build_scenario(session, ready=1)
    # Same configuration (deduplicated by hash), document of another corpus: the chunk
    # exists but the set cannot use it.
    elsewhere = await build_scenario(session, ready=1)
    qa_set_id = await _qa_set(client, scenario)
    chunk = (await _chunks(session, elsewhere.ready[0], scenario.configuration))[0]
    question = await _question(client, qa_set_id)

    response = await client.put(
        f"{QUESTIONS}/{question['id']}/evidence",
        json={
            "chunking_configuration_id": scenario.configuration_id,
            "status": "confirmed",
            "annotator": "anna",
            "chunks": [{"chunk_id": str(chunk.id), "relevance": "sufficient"}],
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "documents_not_in_origin_corpus"


async def test_coverage_and_listing_report_the_evidence_status(client, session) -> None:
    scenario = await build_scenario(session, ready=1)
    qa_set_id = await _qa_set(client, scenario)
    chunk = (await _chunks(session, scenario.ready[0], scenario.configuration))[0]
    confirmed = await _question(client, qa_set_id, text="Confirmed?")
    missing = await _question(client, qa_set_id, text="Not found?")
    await _question(client, qa_set_id, text="Untouched?")
    await _question(client, qa_set_id, text="Unanswerable?", answerable=False)
    base = {"chunking_configuration_id": scenario.configuration_id, "annotator": "a"}
    await client.put(
        f"{QUESTIONS}/{confirmed['id']}/evidence",
        json={
            **base,
            "status": "confirmed",
            "chunks": [{"chunk_id": str(chunk.id), "relevance": "sufficient"}],
        },
    )
    await client.put(
        f"{QUESTIONS}/{missing['id']}/evidence", json={**base, "status": "not_found"}
    )

    coverage = await client.get(
        f"{QA_SETS}/{qa_set_id}/evidence-coverage",
        params={"chunking_configuration_id": scenario.configuration_id},
    )
    listed = await client.get(
        f"{QA_SETS}/{qa_set_id}",
        params={"chunking_configuration_id": scenario.configuration_id},
    )

    assert coverage.json() | {"qa_set_id": None, "chunking_configuration_id": None} == {
        "qa_set_id": None,
        "chunking_configuration_id": None,
        "answerable": 3,
        "not_answerable": 1,
        "confirmed": 1,
        "not_found": 1,
        "to_review": 0,
        "not_reviewed": 1,
        # One of the two reviewed questions has no evidence under this configuration.
        "recall_ceiling": 0.5,
    }
    assert [q["evidence_status"] for q in listed.json()["questions"]["items"]] == [
        "confirmed",
        "not_found",
        "not_reviewed",
        "not_reviewed",
    ]
    plain = (await client.get(f"{QA_SETS}/{qa_set_id}")).json()
    assert plain["questions"]["items"][0]["evidence_status"] is None


# --------------------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------------------


async def test_export_then_import_recreates_the_questions(client, session) -> None:
    scenario = await build_scenario(session, ready=1)
    twin = await make_document(session, scenario.ready[0].filename)
    session.add(CorpusDocument(corpus_id=scenario.corpus.id, document_id=twin.id))
    plain = await make_document(session, "plain.pdf")
    session.add(CorpusDocument(corpus_id=scenario.corpus.id, document_id=plain.id))
    # Real sha-256 values: the ambiguous name is exported by hash and read back as one.
    scenario.ready[0].content_hash = "ab" * 32
    twin.content_hash = "cd" * 32
    await session.flush()
    qa_set_id = await _qa_set(client, scenario)
    await _question(
        client,
        qa_set_id,
        text='A question, with "quotes"?',
        tags=["x", "y"],
        expected_answers=[{"text": "Yes, it is"}],
        gold_document_ids=[str(twin.id), str(plain.id)],
    )
    await _question(client, qa_set_id, text="No answer?", answerable=False)

    for export_format in ("csv", "jsonl"):
        exported = await client.get(
            f"{QA_SETS}/{qa_set_id}/export", params={"format": export_format}
        )
        assert exported.status_code == 200, exported.text
        assert "attachment" in exported.headers["content-disposition"]

        target = await _qa_set(client, scenario)
        imported = await client.post(
            f"{QA_SETS}/{target}/import",
            files={"file": (f"export.{export_format}", exported.content, "text/plain")},
        )
        summary = imported.json()
        assert summary["unresolved"] == summary["ambiguous"] == summary["invalid"] == []
        assert len(summary["imported"]) == 2

        items = (await client.get(f"{QA_SETS}/{target}")).json()["questions"]["items"]
        first = items[0]
        assert first["text"] == 'A question, with "quotes"?'
        assert first["tags"] == ["x", "y"]
        assert first["expected_answers"] == [{"text": "Yes, it is", "is_primary": True}]
        assert {g["document_id"] for g in first["gold_documents"]} == {
            str(twin.id),
            str(plain.id),
        }
        assert items[1]["answerable"] is False


async def test_export_names_an_ambiguous_file_by_hash(client, session) -> None:
    scenario = await build_scenario(session, ready=1)
    document = scenario.ready[0]
    twin = await make_document(session, document.filename)
    session.add(CorpusDocument(corpus_id=scenario.corpus.id, document_id=twin.id))
    await session.flush()
    qa_set_id = await _qa_set(client, scenario)
    await _question(client, qa_set_id, gold_document_ids=[str(document.id)])

    exported = await client.get(
        f"{QA_SETS}/{qa_set_id}/export", params={"format": "jsonl"}
    )

    row = json.loads(exported.text.splitlines()[0])
    assert row["gold_files"] == [f"sha256:{document.content_hash}"]


async def test_export_of_a_snapshot_keeps_the_replaced_question(
    client, session
) -> None:
    scenario = await build_scenario(session, ready=1)
    qa_set_id = await _qa_set(client, scenario)
    question = await _question(client, qa_set_id, text="Old wording?")
    snapshot = (await client.post(f"{QA_SETS}/{qa_set_id}/snapshots", json={})).json()[
        "snapshot"
    ]
    await client.post(
        f"{QUESTIONS}/{question['id']}/replace", json={"text": "New wording?"}
    )

    current = await client.get(
        f"{QA_SETS}/{qa_set_id}/export", params={"format": "csv"}
    )
    frozen = await client.get(
        f"{QA_SETS}/{qa_set_id}/export",
        params={"format": "csv", "snapshot_id": snapshot["id"]},
    )

    assert "New wording?" in current.text and "Old wording?" not in current.text
    assert "Old wording?" in frozen.text and "New wording?" not in frozen.text
