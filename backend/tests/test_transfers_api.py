from __future__ import annotations

import dataclasses
import uuid

import pytest
from sqlalchemy import select
from src.artifacts.models import Chunk, ChunkResult
from src.components.builtin.embedder import openai_embedder
from src.infrastructure.database.enums import ComponentType
from src.pipelines.models import ChunkingConfiguration
from src.pipelines.service import ProfileService
from src.transfers.ranking import TransferRanker
from tests.pipeline_factory import (
    Scenario,
    build_scenario,
    make_configuration,
    materialise,
)
from tests.retrieval_factory import version_id

pytestmark = pytest.mark.integration

QA_SETS = "/api/v1/qa-sets"
QUESTIONS = "/api/v1/questions"
TRANSFERS = "/api/v1/transfers"

PENALTY = (
    "La penale per ritardo nella consegna è pari all'1 per mille dell'importo "
    "contrattuale per ogni giorno lavorativo di ritardo, fino al 10 per cento."
)
# The same passage as another parser extracts it: ligature, typographic apostrophes, a
# word split across lines.
PENALTY_REPARSED = (
    "La penale per ritardo nella con-\nsegna è pari all’1 per mille dell’importo\n"
    "contrattuale per ogni giorno lavorativo di ritardo, ﬁno al 10 per cento."
)
SOURCE_TEXTS = {
    "ready-0.pdf": [
        "Premessa. Il presente capitolato disciplina la fornitura di servizi informatici.",
        PENALTY,
        "Assistenza tecnica dal lunedì al venerdì dalle nove alle diciotto.",
    ],
    "ready-1.pdf": [
        "Il pagamento delle fatture avviene a sessanta giorni dalla data di ricezione.",
        "Le fatture sono trasmesse esclusivamente in formato elettronico.",
        "Le parti si impegnano a mantenere riservate le informazioni scambiate.",
    ],
}
TARGET_TEXTS = {
    "ready-0.pdf": [
        "Premessa.\nIl presente capitolato disciplina la fornitura di servizi informatici.",
        "Assistenza tecnica dal lunedì al venerdì, dalle nove alle diciotto.",
        PENALTY_REPARSED,
    ],
    "ready-1.pdf": [
        "Le parti si impegnano a mantenere riservate le informazioni scambiate.",
        "Il pagamento delle fatture avviene a sessanta giorni dalla data di ricezione.",
        "Le fatture sono trasmesse esclusivamente in formato elettronico.",
    ],
}


@dataclasses.dataclass
class World:
    """A corpus chunked by two configurations and a set of three questions over it."""

    scenario: Scenario
    source: ChunkingConfiguration
    target: ChunkingConfiguration
    embedding_profile_id: str
    qa_set_id: str
    penalty: str
    payment: str
    missing: str


async def _chunks(session, document, configuration_id) -> list[Chunk]:
    stmt = (
        select(Chunk)
        .join(ChunkResult, ChunkResult.id == Chunk.chunk_result_id)
        .where(
            ChunkResult.document_id == document.id,
            ChunkResult.chunking_configuration_id == configuration_id,
        )
        .order_by(Chunk.ordinal)
    )
    return list((await session.scalars(stmt)).all())


async def _write_texts(session, scenario, configuration, texts) -> None:
    for document in scenario.ready:
        for chunk, text in zip(
            await _chunks(session, document, configuration.id),
            texts[document.filename],
            strict=True,
        ):
            chunk.text = text
    await session.flush()


async def _question(client, qa_set_id, text, answer, gold) -> str:
    response = await client.post(
        f"{QA_SETS}/{qa_set_id}/questions",
        json={
            "text": text,
            "expected_answers": [{"text": answer, "is_primary": True}],
            "gold_document_ids": [str(document.id) for document in gold],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.fixture
async def world(client, session, fake_engine) -> World:
    scenario = await build_scenario(session, ready=2, missing=1, chunks_per_document=3)
    await _write_texts(session, scenario, scenario.configuration, SOURCE_TEXTS)
    _, target = await make_configuration(session, chunk_size=300)
    for document in scenario.ready:
        await materialise(
            session, document, scenario.parsing_profile, target, chunk_count=3
        )
    await _write_texts(session, scenario, target, TARGET_TEXTS)
    embedding, _ = await ProfileService(session).get_or_create_embedding_profile(
        name="fake",
        component_version_id=await version_id(
            session, ComponentType.EMBEDDER, openai_embedder.KEY
        ),
    )
    created = await client.post(
        QA_SETS, json={"name": "qa", "origin_corpus_id": scenario.corpus_id}
    )
    qa_set_id = created.json()["id"]
    ready_0, ready_1 = scenario.ready
    return World(
        scenario=scenario,
        source=scenario.configuration,
        target=target,
        embedding_profile_id=str(embedding.id),
        qa_set_id=qa_set_id,
        penalty=await _question(
            client,
            qa_set_id,
            "Qual è la penale per ritardo nella consegna?",
            "L'1 per mille dell'importo contrattuale per giorno.",
            [ready_0],
        ),
        payment=await _question(
            client,
            qa_set_id,
            "Entro quanti giorni sono pagate le fatture?",
            "A sessanta giorni dalla ricezione.",
            [ready_1],
        ),
        missing=await _question(
            client,
            qa_set_id,
            "Cosa dice il documento mai materializzato?",
            "Non si sa.",
            [scenario.missing[0]],
        ),
    )


async def _evidence(client, question_id, configuration, status, chunks=()) -> None:
    response = await client.put(
        f"{QUESTIONS}/{question_id}/evidence",
        json={
            "chunking_configuration_id": str(configuration.id),
            "status": status,
            "annotator": "anna",
            "chunks": [
                {"chunk_id": str(chunk_id), "relevance": relevance}
                for chunk_id, relevance in chunks
            ],
        },
    )
    assert response.status_code == 200, response.text


async def _create(client, world: World, **overrides) -> dict:
    body = {
        "qa_set_id": world.qa_set_id,
        "target_configuration_id": str(world.target.id),
        "embedding_profile_id": world.embedding_profile_id,
        "exclude_uncovered": True,
        **overrides,
    }
    response = await client.post(TRANSFERS, json=body)
    assert response.status_code == 202, response.text
    return response.json()


async def _rank_all(session, job_id: str) -> None:
    """Do in-process what the workflow does: rank every question, then close the job."""
    ranker = TransferRanker(session)
    job = uuid.UUID(job_id)
    await ranker.open_job(job)
    for item in await ranker.unfinished_ids(job, after_id=None, limit=100):
        await ranker.rank(item)
    await ranker.finish_job(job)


async def _review(client, job_id: str, question_id: str) -> dict:
    response = await client.get(f"{TRANSFERS}/{job_id}/questions/{question_id}")
    assert response.status_code == 200, response.text
    return response.json()


# -- creation -----------------------------------------------------------------------------


async def test_questions_whose_documents_have_no_chunks_need_an_explicit_choice(
    client, world, fake_workflows
) -> None:
    refused = await client.post(
        TRANSFERS,
        json={
            "qa_set_id": world.qa_set_id,
            "target_configuration_id": str(world.target.id),
        },
    )

    assert refused.status_code == 422
    body = refused.json()
    assert body["code"] == "uncovered_questions_choice_required"
    [uncovered] = body["details"]["uncovered_questions"]
    assert uncovered["question_id"] == world.missing
    assert uncovered["reason"] == "documents_not_materialised"
    assert [doc["filename"] for doc in uncovered["missing_documents"]] == [
        "missing-0.pdf"
    ]

    job = await _create(client, world)
    assert [item["question_id"] for item in job["excluded"]] == [world.missing]
    assert job["progress"]["total"] == 2
    assert job["status"] == "pending"
    assert fake_workflows.started[-1].workflow == "TransferDatasetWorkflow"


async def test_questions_already_decided_in_the_target_are_never_proposed_again(
    client, session, world
) -> None:
    target_chunk = (await _chunks(session, world.scenario.ready[0], world.target.id))[2]
    await _evidence(
        client,
        world.penalty,
        world.target,
        "confirmed",
        [(target_chunk.id, "sufficient")],
    )

    job = await _create(client, world)

    assert job["progress"]["total"] == 1
    assert job["skipped"] == {"already_decided": 1}
    await _evidence(client, world.payment, world.target, "not_found")
    nothing = await client.post(
        TRANSFERS,
        json={
            "qa_set_id": world.qa_set_id,
            "target_configuration_id": str(world.target.id),
            "exclude_uncovered": True,
        },
    )
    assert nothing.status_code == 422
    assert nothing.json()["code"] == "nothing_to_transfer"


async def test_a_transfer_takes_only_the_questions_confirmed_in_the_source(
    client, session, world
) -> None:
    source_chunk = (await _chunks(session, world.scenario.ready[0], world.source.id))[1]
    await _evidence(
        client,
        world.penalty,
        world.source,
        "confirmed",
        [(source_chunk.id, "sufficient")],
    )

    job = await _create(client, world, source_configuration_id=str(world.source.id))

    assert job["progress"]["total"] == 1
    # The other two, the one never materialised included, have nothing to transfer.
    assert job["skipped"] == {"not_confirmed_in_source": 2}
    same = await client.post(
        TRANSFERS,
        json={
            "qa_set_id": world.qa_set_id,
            "target_configuration_id": str(world.target.id),
            "source_configuration_id": str(world.target.id),
        },
    )
    assert same.status_code == 422
    assert same.json()["code"] == "same_configuration"


# -- ranking ------------------------------------------------------------------------------


async def test_a_transfer_finds_the_same_passage_and_preselects_it(
    client, session, world
) -> None:
    source_chunk = (await _chunks(session, world.scenario.ready[0], world.source.id))[1]
    await _evidence(
        client,
        world.penalty,
        world.source,
        "confirmed",
        [(source_chunk.id, "supporting")],
    )
    job = await _create(client, world, source_configuration_id=str(world.source.id))

    await _rank_all(session, job["id"])
    review = await _review(client, job["id"], world.penalty)

    target_chunk = (await _chunks(session, world.scenario.ready[0], world.target.id))[2]
    top = review["candidates"][0]
    assert top["chunk_id"] == str(target_chunk.id)
    assert top["lexical_score"] >= 0.95
    assert (top["preselected"], top["confidence"]) == (True, "high")
    # The grade given in the source is carried over as a suggestion.
    assert top["suggested_relevance"] == "supporting"
    assert top["semantic_score"] is not None and top["positional_score"] is not None
    # Every chunk of the gold document is a candidate: no cutoff.
    assert len(review["candidates"]) == 3
    assert not any(candidate["preselected"] for candidate in review["candidates"][1:])
    assert [chunk["text"] for chunk in review["reference"]] == [PENALTY]
    assert review["state"] == "preselected"
    # Pre-selected is not confirmed: nothing was written to the evidence.
    assert review["evidence_status"] == "not_reviewed"


async def test_a_proposal_without_source_ranks_by_the_question_and_never_preselects(
    client, session, world
) -> None:
    job = await _create(client, world)

    await _rank_all(session, job["id"])
    review = await _review(client, job["id"], world.payment)

    # The fake embedder of the tests is not semantic: the order is checked without it.
    assert len(review["candidates"]) == 3
    assert review["candidates"][0]["semantic_score"] is not None
    assert review["candidates"][0]["positional_score"] is None
    assert not any(candidate["preselected"] for candidate in review["candidates"])
    assert review["reference"] == []
    done = (await client.get(f"{TRANSFERS}/{job['id']}")).json()
    assert done["status"] == "completed"
    assert done["progress"]["ranked"] == 2


async def test_without_an_embedder_the_ranking_rests_on_the_words(
    client, session, world
) -> None:
    job = await _create(client, world, embedding_profile_id=None)
    assert job["embedding_profile_id"] is None

    await _rank_all(session, job["id"])
    review = await _review(client, job["id"], world.payment)

    assert review["candidates"][0]["semantic_score"] is None
    payment_chunk = (await _chunks(session, world.scenario.ready[1], world.target.id))[
        1
    ]
    assert review["candidates"][0]["chunk_id"] == str(payment_chunk.id)


async def test_a_ranked_question_is_not_ranked_again(client, session, world) -> None:
    job = await _create(client, world)
    await _rank_all(session, job["id"])
    ranker = TransferRanker(session)

    assert (
        await ranker.unfinished_ids(uuid.UUID(job["id"]), after_id=None, limit=10) == []
    )
    resumed = await client.post(f"{TRANSFERS}/{job['id']}/resume")
    assert resumed.status_code == 409
    assert resumed.json()["code"] == "transfer_not_resumable"


# -- review -------------------------------------------------------------------------------


async def test_the_decision_is_the_evidence_and_moves_progress_and_ceiling(
    client, session, world
) -> None:
    job = await _create(client, world)
    await _rank_all(session, job["id"])
    queue = (await client.get(f"{TRANSFERS}/{job['id']}/questions")).json()
    assert {row["state"] for row in queue["items"]} <= {"to_review", "no_candidates"}

    review = await _review(client, job["id"], world.payment)
    assert review["next_question_id"] == world.penalty
    await _evidence(
        client,
        world.payment,
        world.target,
        "confirmed",
        [(review["candidates"][0]["chunk_id"], "sufficient")],
    )
    await _evidence(client, world.penalty, world.target, "not_found")

    after = (await client.get(f"{TRANSFERS}/{job['id']}")).json()
    assert after["progress"] | {"total": 0, "ranked": 0, "failed": 0} == {
        "total": 0,
        "ranked": 0,
        "failed": 0,
        "reviewed": 2,
        "confirmed": 1,
        "not_found": 1,
    }
    assert after["recall_ceiling"] == 0.5
    decided = (
        await client.get(
            f"{TRANSFERS}/{job['id']}/questions", params={"state": "decided"}
        )
    ).json()
    assert decided["total"] == 2
    assert (await _review(client, job["id"], world.payment))["next_question_id"] is None


async def test_a_question_outside_the_job_is_not_found(client, world) -> None:
    job = await _create(client, world)

    response = await client.get(f"{TRANSFERS}/{job['id']}/questions/{world.missing}")

    assert response.status_code == 404
    assert response.json()["code"] == "question_not_in_transfer"


async def test_a_job_is_cancelled_once(client, world, fake_workflows) -> None:
    job = await _create(client, world)

    cancelled = await client.post(f"{TRANSFERS}/{job['id']}/cancel")
    again = await client.post(f"{TRANSFERS}/{job['id']}/cancel")

    assert cancelled.json()["status"] == "cancelled"
    assert fake_workflows.cancelled == [f"transfer-dataset-{job['id']}"]
    assert again.status_code == 409
    listed = (await client.get(TRANSFERS, params={"qa_set_id": world.qa_set_id})).json()
    assert [item["id"] for item in listed["items"]] == [job["id"]]


# -- full-text search ---------------------------------------------------------------------


async def test_chunks_are_found_by_their_text_in_a_configuration(client, world) -> None:
    response = await client.get(
        "/api/v1/chunks/search",
        params={
            "chunking_configuration_id": str(world.target.id),
            "corpus_id": world.scenario.corpus_id,
            "q": "FORMATO elettronico",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["filename"] == "ready-1.pdf"
    # Words split by a line break in the chunk are still found as one phrase.
    across_lines = await client.get(
        "/api/v1/chunks/search",
        params={
            "chunking_configuration_id": str(world.target.id),
            "q": "Premessa. Il presente",
        },
    )
    assert across_lines.json()["total"] == 1
    wildcard = await client.get(
        "/api/v1/chunks/search",
        params={"chunking_configuration_id": str(world.target.id), "q": "%%"},
    )
    assert wildcard.json()["total"] == 0


async def test_an_embedder_failure_is_raised_for_the_workflow_to_retry(
    client, session, world, monkeypatch
) -> None:
    from src.retrieval.embedders import BUILTIN_EMBEDDERS
    from src.retrieval.exceptions import RetrievalBackendError

    def broken(params):
        raise RuntimeError("rate limited")

    job = await _create(client, world)
    ranker = TransferRanker(session)
    await ranker.open_job(uuid.UUID(job["id"]))
    [first, *_] = await ranker.unfinished_ids(
        uuid.UUID(job["id"]), after_id=None, limit=10
    )
    monkeypatch.setitem(BUILTIN_EMBEDDERS, openai_embedder.KEY, broken)

    with pytest.raises(RetrievalBackendError):
        await ranker.rank(first)

    # Still unranked, so a retry or a resumed job picks it up.
    assert first in await ranker.unfinished_ids(
        uuid.UUID(job["id"]), after_id=None, limit=10
    )
