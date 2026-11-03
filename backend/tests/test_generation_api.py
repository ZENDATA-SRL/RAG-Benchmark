from __future__ import annotations

import uuid

import pytest
from src.generation.runner import GenerationRunner
from src.infrastructure.temporal.workflow_ids import GENERATE_QUESTIONS_WORKFLOW
from tests.generation_factory import (
    GENERATED_QUESTIONS,
    GENERATION_JOBS,
    QA_SETS,
    build_corpus,
    scripted,
    submit,
    tool_call,
)

pytestmark = pytest.mark.integration

PENALTY = "La penale per ritardo nella consegna è pari all'1 per mille"
DURATION = "Il contratto ha una durata di tre anni"
REFERENT = "Il fornitore nomina un referente tecnico entro dieci giorni"
SUPPORT = "L'assistenza tecnica è garantita dal lunedì al venerdì"


@pytest.fixture(autouse=True)
def credentials(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")


def _body(corpus, **overrides) -> dict:
    return {
        "qa_set_id": corpus.qa_set_id,
        "chunking_configuration_id": corpus.configuration_id,
        "per_document": 2,
        "cross_document": 3,
        "provider": "openai",
        "model": "gpt-test",
        **overrides,
    }


async def _create(client, corpus, **overrides) -> dict:
    response = await client.post(GENERATION_JOBS, json=_body(corpus, **overrides))
    assert response.status_code == 202, response.text
    return response.json()


async def _generate(session, client, corpus) -> tuple[dict, list[dict]]:
    """A job whose first document unit and cross unit proposed three questions."""
    job = await _create(client, corpus, per_document=2, cross_document=1)
    units = (await client.get(f"{GENERATION_JOBS}/{job['id']}/units")).json()
    document_unit = next(u for u in units if u["phase"] == "document")
    cross_unit = next(u for u in units if u["phase"] == "cross")
    runner = GenerationRunner(
        session,
        chat_model=scripted(
            submit(
                "Quanto costa ogni giorno di ritardo?",
                "L'1 per mille dell'importo.",
                ("d1:c1", PENALTY),
            ),
            submit(
                "Per quanti anni vale il contratto?", "Tre anni.", ("d1:c3", DURATION)
            ),
            tool_call("finish", summary="Capitolato."),
        ),
    )
    await runner.run_unit(uuid.UUID(document_unit["id"]))
    runner.chat_model = scripted(
        submit(
            "Chi coordina l'assistenza e in che giorni è garantita?",
            "Il referente tecnico, nei giorni feriali.",
            ("d1:c2", SUPPORT),
            ("d3:c1", "Il referente tecnico coordina gli interventi di assistenza"),
        ),
        tool_call("finish"),
    )
    await runner.run_unit(uuid.UUID(cross_unit["id"]))
    queue = await client.get(f"{GENERATION_JOBS}/{job['id']}/proposals")
    assert queue.status_code == 200, queue.text
    return job, queue.json()["items"]


async def test_estimate_and_create_launch_the_workflow(session, client, fake_workflows):
    corpus = await build_corpus(session, client)

    estimate = await client.post(f"{GENERATION_JOBS}/estimate", json=_body(corpus))
    assert estimate.status_code == 200, estimate.text
    assert [d["filename"] for d in estimate.json()["documents"]] == [
        "ready-0.pdf",
        "ready-1.pdf",
        "ready-2.pdf",
    ]
    assert estimate.json()["estimate"] == {
        "documents": 3,
        "document_units": 3,
        "cross_units": 1,
        "max_steps": 40,
        "max_model_calls": 160,
        "target_questions": 9,
    }

    job = await _create(client, corpus, cross_document=7, max_steps=10)
    assert job["status"] == "pending"
    assert job["prompt_version"] == "1"
    assert job["params"]["limits"]["max_chunks"] == 4
    assert job["estimate"]["cross_units"] == 2
    assert job["progress"]["document"]["units"] == 3
    assert job["progress"]["cross"]["target"] == 7
    [started] = fake_workflows.started
    assert started.workflow == GENERATE_QUESTIONS_WORKFLOW
    assert started.arg["generation_job_id"] == job["id"]

    units = (await client.get(f"{GENERATION_JOBS}/{job['id']}/units")).json()
    assert [(u["phase"], u["target"]) for u in units] == [
        ("document", 2),
        ("document", 2),
        ("document", 2),
        ("cross", 5),
        ("cross", 2),
    ]
    assert [u["filename"] for u in units[:3]] == [
        "ready-0.pdf",
        "ready-1.pdf",
        "ready-2.pdf",
    ]
    listed = await client.get(GENERATION_JOBS, params={"qa_set_id": corpus.qa_set_id})
    assert listed.json()["total"] == 1


async def test_unmaterialised_documents_must_be_excluded(session, client):
    corpus = await build_corpus(session, client, unmaterialised=1)

    refused = await client.post(GENERATION_JOBS, json=_body(corpus))
    assert refused.status_code == 422
    error = refused.json()
    assert error["code"] == "unmaterialized_documents_choice_required"
    [missing] = error["details"]["unmaterialized_documents"]
    assert missing["filename"] == "missing-0.pdf"

    job = await _create(client, corpus, exclude_unmaterialized=True)
    assert len(job["document_ids"]) == 3
    assert [item["filename"] for item in job["excluded"]] == ["missing-0.pdf"]

    excluded = await _create(
        client, corpus, excluded_document_ids=[str(corpus.scenario.missing[0].id)]
    )
    assert excluded["excluded"] == []


async def test_only_the_chosen_documents(session, client):
    corpus = await build_corpus(session, client)
    chosen = [str(corpus.documents[2].id), str(corpus.documents[0].id)]

    estimate = await client.post(
        f"{GENERATION_JOBS}/estimate",
        json=_body(corpus, document_ids=chosen, per_document=1, cross_document=1),
    )
    assert estimate.status_code == 200, estimate.text
    assert estimate.json()["estimate"]["documents"] == 2
    left_out = {d["document_id"] for d in estimate.json()["documents"] if d["excluded"]}
    assert left_out == {str(corpus.documents[1].id)}

    job = await _create(
        client, corpus, document_ids=chosen, per_document=1, cross_document=1
    )
    # The order of the corpus, which the short references follow.
    assert job["document_ids"] == [chosen[1], chosen[0]]
    units = (await client.get(f"{GENERATION_JOBS}/{job['id']}/units")).json()
    assert {u["document_id"] for u in units if u["phase"] == "document"} == set(chosen)

    outside = await client.post(
        GENERATION_JOBS, json=_body(corpus, document_ids=[str(uuid.uuid4())])
    )
    assert outside.status_code == 422
    assert outside.json()["code"] == "documents_outside_corpus"

    alone = await client.post(
        GENERATION_JOBS, json=_body(corpus, document_ids=chosen[:1])
    )
    assert alone.json()["code"] == "cross_needs_two_documents"


async def test_refused_jobs(session, client):
    corpus = await build_corpus(session, client)
    orphan = await client.post(QA_SETS, json={"name": "no corpus"})
    no_corpus = await client.post(
        GENERATION_JOBS, json=_body(corpus, qa_set_id=orphan.json()["id"])
    )
    assert no_corpus.json()["code"] == "qa_set_without_corpus"

    nothing = await client.post(
        GENERATION_JOBS, json=_body(corpus, per_document=0, cross_document=0)
    )
    assert nothing.json()["code"] == "nothing_to_generate"

    others = [str(document.id) for document in corpus.documents[1:]]
    alone = await client.post(
        GENERATION_JOBS, json=_body(corpus, excluded_document_ids=others)
    )
    assert alone.status_code == 422
    assert alone.json()["code"] == "cross_needs_two_documents"


async def test_queue_and_accept_with_corrections(session, client):
    corpus = await build_corpus(session, client)
    job, proposals = await _generate(session, client, corpus)
    assert [p["kind"] for p in proposals] == ["single", "single", "cross"]
    penalty, duration, cross = proposals
    assert penalty["chunks"][0]["quote"] == PENALTY
    assert penalty["chunks"][0]["relevance"] == "sufficient"
    assert penalty["chunks"][0]["filename"] == "ready-0.pdf"

    opened = await client.get(f"{GENERATED_QUESTIONS}/{penalty['id']}")
    assert opened.status_code == 200, opened.text
    assert opened.json()["phase"] == "document"
    assert opened.json()["next_proposal_id"] == duration["id"]

    accepted = await client.post(
        f"{GENERATED_QUESTIONS}/{penalty['id']}/accept",
        json={
            "text": "Qual è la penale giornaliera per il ritardo nella consegna?",
            "answer": penalty["answer"],
            "chunks": [
                {
                    "chunk_id": penalty["chunks"][0]["chunk_id"],
                    "relevance": "sufficient",
                }
            ],
            "annotator": "anna",
        },
    )
    assert accepted.status_code == 200, accepted.text
    decision = accepted.json()
    assert decision["proposal"]["status"] == "accepted"
    # The proposal keeps the text the agent wrote.
    assert decision["proposal"]["text"] == "Quanto costa ogni giorno di ritardo?"
    assert decision["next_proposal_id"] == duration["id"]

    question_id = decision["question_id"]
    question = (
        await client.get(
            f"/api/v1/questions/{question_id}",
            params={"chunking_configuration_id": corpus.configuration_id},
        )
    ).json()
    assert (
        question["text"]
        == "Qual è la penale giornaliera per il ritardo nella consegna?"
    )
    assert question["tags"] == ["generated", "generated:single"]
    assert question["expected_answers"] == [
        {"text": "L'1 per mille dell'importo.", "is_primary": True}
    ]
    assert [g["filename"] for g in question["gold_documents"]] == ["ready-0.pdf"]
    assert question["evidence_status"] == "confirmed"

    # The cross one becomes a single question if the reviewer keeps only one chunk.
    narrowed = await client.post(
        f"{GENERATED_QUESTIONS}/{cross['id']}/accept",
        json={
            "text": cross["text"],
            "answer": cross["answer"],
            "chunks": [
                {"chunk_id": chunk["chunk_id"], "relevance": "supporting"}
                for chunk in cross["chunks"]
            ],
            "annotator": "anna",
        },
    )
    assert narrowed.status_code == 200, narrowed.text
    cross_question = (
        await client.get(f"/api/v1/questions/{narrowed.json()['question_id']}")
    ).json()
    assert cross_question["tags"] == ["generated", "generated:cross"]
    assert sorted(g["filename"] for g in cross_question["gold_documents"]) == [
        "ready-0.pdf",
        "ready-2.pdf",
    ]

    view = (await client.get(f"{GENERATION_JOBS}/{job['id']}")).json()
    assert view["progress"]["proposals"]["accepted"] == 2
    assert view["progress"]["proposals"]["pending"] == 1
    assert view["progress"]["documents_covered"] == 2
    assert view["progress"]["combinations"] == 1


async def test_decisions_are_taken_once(session, client):
    corpus = await build_corpus(session, client)
    _, proposals = await _generate(session, client, corpus)
    penalty, duration, _ = proposals
    body = {
        "text": penalty["text"],
        "answer": penalty["answer"],
        "chunks": [
            {"chunk_id": penalty["chunks"][0]["chunk_id"], "relevance": "sufficient"}
        ],
        "annotator": "anna",
    }
    first = await client.post(
        f"{GENERATED_QUESTIONS}/{penalty['id']}/accept", json=body
    )
    assert first.status_code == 200, first.text
    again = await client.post(
        f"{GENERATED_QUESTIONS}/{penalty['id']}/accept", json=body
    )
    assert again.status_code == 409
    assert again.json()["code"] == "generated_question_already_reviewed"

    rejected = await client.post(
        f"{GENERATED_QUESTIONS}/{duration['id']}/reject", json={"annotator": "anna"}
    )
    assert rejected.status_code == 200
    assert rejected.json()["proposal"]["status"] == "rejected"
    detail = await client.get(f"{QA_SETS}/{corpus.qa_set_id}")
    assert [q["text"] for q in detail.json()["questions"]["items"]] == [penalty["text"]]
    pending = await client.get(
        f"{GENERATION_JOBS}/{penalty['generation_job_id']}/proposals",
        params={"status": "pending"},
    )
    assert pending.json()["total"] == 1


async def test_accept_refuses_chunks_outside_the_job(session, client):
    corpus = await build_corpus(session, client)
    job = await _create(
        client,
        corpus,
        per_document=1,
        cross_document=0,
        excluded_document_ids=[str(corpus.documents[2].id)],
    )
    units = (await client.get(f"{GENERATION_JOBS}/{job['id']}/units")).json()
    await GenerationRunner(
        session,
        chat_model=scripted(
            submit("Quanto costa il ritardo?", "L'1 per mille.", ("d1:c1", PENALTY)),
            tool_call("finish", summary="s"),
        ),
    ).run_unit(uuid.UUID(units[0]["id"]))
    [proposal] = (await client.get(f"{GENERATION_JOBS}/{job['id']}/proposals")).json()[
        "items"
    ]

    for chunk_id in (corpus.chunks["ready-2.pdf"][0].id, uuid.uuid4()):
        response = await client.post(
            f"{GENERATED_QUESTIONS}/{proposal['id']}/accept",
            json={
                "text": proposal["text"],
                "answer": proposal["answer"],
                "chunks": [{"chunk_id": str(chunk_id), "relevance": "sufficient"}],
                "annotator": "anna",
            },
        )
        assert response.status_code == 422
        assert response.json()["code"] == "chunks_outside_job"


async def test_cancel_and_resume(session, client, fake_workflows):
    corpus = await build_corpus(session, client)
    job = await _create(client, corpus)

    cancelled = await client.post(f"{GENERATION_JOBS}/{job['id']}/cancel")
    assert cancelled.json()["status"] == "cancelled"
    assert fake_workflows.cancelled == [f"generate-questions-{job['id']}"]
    again = await client.post(f"{GENERATION_JOBS}/{job['id']}/cancel")
    assert again.status_code == 409

    resumed = await client.post(f"{GENERATION_JOBS}/{job['id']}/resume")
    assert resumed.status_code == 202
    assert resumed.json()["status"] == "pending"
    assert len(fake_workflows.started) == 2


async def test_missing_credentials_fail_the_job_at_opening(
    session, client, monkeypatch
):
    corpus = await build_corpus(session, client)
    job = await _create(client, corpus)
    monkeypatch.delenv("OPENAI_API_KEY")

    opened = await GenerationRunner(session).open_job(uuid.UUID(job["id"]))

    assert opened is False
    view = (await client.get(f"{GENERATION_JOBS}/{job['id']}")).json()
    assert view["status"] == "failed"
    assert view["error"].startswith("missing_credentials")
