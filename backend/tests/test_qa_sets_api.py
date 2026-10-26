from __future__ import annotations

import json
import uuid

import pytest
from src.corpora.models import Corpus, CorpusDocument
from tests.pipeline_factory import make_document

pytestmark = pytest.mark.integration

QA_SETS = "/api/v1/qa-sets"
CSV = "text/csv"


async def _corpus_with(session, *filenames: str):
    corpus = Corpus(name=f"corpus {uuid.uuid4().hex[:6]}")
    session.add(corpus)
    await session.flush()
    documents = {}
    for filename in filenames:
        document = await make_document(session, filename)
        session.add(CorpusDocument(corpus_id=corpus.id, document_id=document.id))
        documents[filename] = document
    await session.flush()
    return corpus, documents


async def _qa_set(client, corpus=None) -> str:
    body = {"name": "qa"}
    if corpus is not None:
        body["origin_corpus_id"] = str(corpus.id)
    response = await client.post(QA_SETS, json=body)
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _import(client, qa_set_id: str, content: str, filename: str = "q.csv"):
    return await client.post(
        f"{QA_SETS}/{qa_set_id}/import",
        files={"file": (filename, content.encode(), CSV)},
    )


async def test_import_resolves_gold_files_by_name_and_lists_the_documents(
    client, session
) -> None:
    corpus, documents = await _corpus_with(session, "a.pdf", "b.pdf")
    qa_set_id = await _qa_set(client, corpus)

    response = await _import(
        client,
        qa_set_id,
        "question,gold_files,tags,answerable\n"
        "What is A?,a.pdf,hr|policy,true\n"
        "Where is B or A?,a.pdf|b.pdf,,\n",
    )

    assert response.status_code == 200, response.text
    summary = response.json()
    assert summary["total_rows"] == 2
    assert [item["text"] for item in summary["imported"]] == [
        "What is A?",
        "Where is B or A?",
    ]
    assert summary["unresolved"] == summary["ambiguous"] == summary["invalid"] == []

    detail = (await client.get(f"{QA_SETS}/{qa_set_id}")).json()
    assert detail["question_count"] == 2
    second = detail["questions"]["items"][1]
    assert {gold["filename"] for gold in second["gold_documents"]} == {"a.pdf", "b.pdf"}
    assert second["answerable"] is True
    first = detail["questions"]["items"][0]
    assert first["tags"] == ["hr", "policy"]
    assert first["gold_documents"][0]["document_id"] == str(documents["a.pdf"].id)
    assert first["expected_answers"] == []


async def test_import_stores_the_expected_answer_as_primary(client, session) -> None:
    corpus, _ = await _corpus_with(session, "a.pdf")
    qa_set_id = await _qa_set(client, corpus)

    response = await _import(
        client,
        qa_set_id,
        'question,answer,gold_files\nWhat is A?,"A is the first, of all",a.pdf\n'
        "Without answer?,,a.pdf\n",
    )

    assert response.status_code == 200, response.text
    items = (await client.get(f"{QA_SETS}/{qa_set_id}")).json()["questions"]["items"]
    assert items[0]["expected_answers"] == [
        {"text": "A is the first, of all", "is_primary": True}
    ]
    assert items[1]["expected_answers"] == []


async def test_unresolved_and_ambiguous_files_are_reported_and_not_imported(
    client, session
) -> None:
    corpus, _ = await _corpus_with(session, "a.pdf", "twin.pdf")
    twin = await make_document(session, "twin.pdf")
    session.add(CorpusDocument(corpus_id=corpus.id, document_id=twin.id))
    await session.flush()
    qa_set_id = await _qa_set(client, corpus)

    response = await _import(
        client,
        qa_set_id,
        "question,gold_files\n"
        "Fine?,a.pdf\n"
        "Missing file?,nowhere.pdf\n"
        "Two files share a name?,twin.pdf\n"
        ",a.pdf\n"
        "No gold?,\n",
    )

    summary = response.json()
    assert [item["text"] for item in summary["imported"]] == ["Fine?"]
    assert summary["unresolved"] == [
        {"row": 2, "question": "Missing file?", "files": ["nowhere.pdf"]}
    ]
    ambiguous = summary["ambiguous"]
    assert len(ambiguous) == 1
    assert ambiguous[0]["row"] == 3
    assert len(ambiguous[0]["files"][0]["candidates"]) == 2
    assert {row["row"] for row in summary["invalid"]} == {4, 5}
    assert summary["total_rows"] == 5


async def test_a_gold_file_can_be_named_by_its_content_hash(client, session) -> None:
    corpus, _ = await _corpus_with(session, "twin.pdf")
    twin = await make_document(session, "twin.pdf")
    session.add(CorpusDocument(corpus_id=corpus.id, document_id=twin.id))
    twin.content_hash = "ab" * 32
    await session.flush()
    qa_set_id = await _qa_set(client, corpus)

    response = await _import(
        client, qa_set_id, f"question,gold_files\nPinned?,sha256:{'ab' * 32}\n"
    )

    summary = response.json()
    assert summary["ambiguous"] == summary["unresolved"] == []
    assert summary["imported"][0]["gold_documents"] == [
        {"document_id": str(twin.id), "filename": "twin.pdf"}
    ]


async def test_reimporting_the_same_file_does_not_duplicate_questions(
    client, session
) -> None:
    corpus, _ = await _corpus_with(session, "a.pdf")
    qa_set_id = await _qa_set(client, corpus)
    content = "question,gold_files\nWhat is A?,a.pdf\n"

    first = (await _import(client, qa_set_id, content)).json()
    second = (await _import(client, qa_set_id, content)).json()

    assert len(first["imported"]) == 1 and first["existing"] == []
    assert second["imported"] == []
    assert second["existing"][0]["question_id"] == first["imported"][0]["question_id"]
    detail = (await client.get(f"{QA_SETS}/{qa_set_id}")).json()
    assert detail["question_count"] == 1


async def test_jsonl_import_with_unanswerable_question(client, session) -> None:
    corpus, _ = await _corpus_with(session, "a.pdf")
    qa_set_id = await _qa_set(client, corpus)
    lines = [
        {
            "question": "Known?",
            "answer": "Yes.",
            "gold_files": ["a.pdf"],
            "tags": ["x"],
        },
        {"question": "Unknowable?", "answerable": False},
        "not json",
    ]
    content = "\n".join(
        line if isinstance(line, str) else json.dumps(line) for line in lines
    )

    response = await _import(client, qa_set_id, content, "q.jsonl")

    summary = response.json()
    assert [item["text"] for item in summary["imported"]] == ["Known?", "Unknowable?"]
    assert summary["invalid"][0]["row"] == 3
    items = (await client.get(f"{QA_SETS}/{qa_set_id}")).json()["questions"]["items"]
    assert [item["answerable"] for item in items] == [True, False]
    assert [item["expected_answers"] for item in items] == [
        [{"text": "Yes.", "is_primary": True}],
        [],
    ]


async def test_an_unsupported_file_is_refused(client, session) -> None:
    qa_set_id = await _qa_set(client)

    response = await _import(client, qa_set_id, "x", "q.xlsx")

    assert response.status_code == 422
    assert response.json()["code"] == "unsupported_import_format"


async def test_freezing_twice_returns_the_same_snapshot(client, session) -> None:
    corpus, _ = await _corpus_with(session, "a.pdf")
    qa_set_id = await _qa_set(client, corpus)
    await _import(client, qa_set_id, "question,gold_files\nOne?,a.pdf\nTwo?,a.pdf\n")

    first = await client.post(f"{QA_SETS}/{qa_set_id}/snapshots", json={})
    second = await client.post(
        f"{QA_SETS}/{qa_set_id}/snapshots", json={"label": "again"}
    )

    assert first.status_code == 201
    assert first.json()["created"] is True
    assert second.json()["created"] is False
    assert second.json()["snapshot"]["id"] == first.json()["snapshot"]["id"]
    assert second.json()["snapshot"]["question_count"] == 2
    assert second.json()["detail"]


async def test_a_new_question_makes_a_new_snapshot(client, session) -> None:
    corpus, _ = await _corpus_with(session, "a.pdf")
    qa_set_id = await _qa_set(client, corpus)
    await _import(client, qa_set_id, "question,gold_files\nOne?,a.pdf\n")
    first = await client.post(f"{QA_SETS}/{qa_set_id}/snapshots", json={})
    await _import(client, qa_set_id, "question,gold_files\nOne?,a.pdf\nTwo?,a.pdf\n")

    second = await client.post(f"{QA_SETS}/{qa_set_id}/snapshots", json={})

    assert second.json()["created"] is True
    assert second.json()["snapshot"]["id"] != first.json()["snapshot"]["id"]
    listing = (await client.get(f"{QA_SETS}/{qa_set_id}/snapshots")).json()
    assert listing["total"] == 2


async def test_freezing_an_empty_set_is_refused(client) -> None:
    qa_set_id = await _qa_set(client)

    response = await client.post(f"{QA_SETS}/{qa_set_id}/snapshots", json={})

    assert response.status_code == 422
    assert response.json()["code"] == "empty_qa_set"


async def test_listing_shows_question_counts(client, session) -> None:
    corpus, _ = await _corpus_with(session, "a.pdf")
    qa_set_id = await _qa_set(client, corpus)
    await _import(client, qa_set_id, "question,gold_files\nOne?,a.pdf\n")

    listing = (await client.get(QA_SETS)).json()

    assert listing["items"][0]["question_count"] == 1
