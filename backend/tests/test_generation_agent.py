from __future__ import annotations

import uuid

import pytest
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import AIMessage
from sqlalchemy import select
from src.generation.models import (
    GeneratedQuestion,
    GeneratedQuestionChunk,
    GenerationUnit,
)
from src.generation.runner import GenerationRunner
from src.generation.service import GenerationService
from src.infrastructure.database.enums import (
    ExecutionStatus,
    GeneratedKind,
    GenerationPhase,
    RelevanceGrade,
)
from tests.generation_factory import (
    build_corpus,
    last_tool_result,
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


async def _job(session, corpus, *, per_document=2, cross_document=0, **params):
    view = await GenerationService(session).create(
        qa_set_id=uuid.UUID(corpus.qa_set_id),
        chunking_configuration_id=corpus.scenario.configuration.id,
        per_document=per_document,
        cross_document=cross_document,
        provider="openai",
        model="gpt-test",
        temperature=0,
        **params,
    )
    return view.job


async def _unit(session, job, phase, position=0) -> GenerationUnit:
    return await session.scalar(
        select(GenerationUnit).where(
            GenerationUnit.generation_job_id == job.id,
            GenerationUnit.phase == phase,
            GenerationUnit.position == position,
        )
    )


async def _proposals(session, unit) -> list[GeneratedQuestion]:
    return list(
        (
            await session.scalars(
                select(GeneratedQuestion)
                .where(GeneratedQuestion.unit_id == unit.id)
                .order_by(GeneratedQuestion.created_at)
            )
        ).all()
    )


async def test_single_chunk_question_is_saved_sufficient(session, client):
    corpus = await build_corpus(session, client)
    job = await _job(session, corpus, per_document=2)
    unit = await _unit(session, job, GenerationPhase.DOCUMENT)
    model = scripted(
        tool_call("document_outline", doc="d1"),
        tool_call("find_chunks", doc="d1", passage=PENALTY),
        submit(
            "Quanto costa ogni giorno di ritardo nella consegna?",
            "L'1 per mille dell'importo contrattuale.",
            ("d1:c1", PENALTY),
        ),
        submit(
            "Per quanti anni vale il contratto?",
            "Tre anni, rinnovabili una volta.",
            ("d1:c3", DURATION),
        ),
        tool_call("finish", summary="Capitolato di servizi.", topics=["penali"]),
    )

    status = await GenerationRunner(session, chat_model=model).run_unit(unit.id)

    assert status == ExecutionStatus.SUCCEEDED
    assert unit.produced == 2
    assert unit.end_reason == "target_reached"
    assert unit.summary == "Capitolato di servizi."
    assert unit.topics == ["penali"]
    proposals = await _proposals(session, unit)
    assert [p.kind for p in proposals] == [GeneratedKind.SINGLE] * 2
    chunk = await session.scalar(
        select(GeneratedQuestionChunk).where(
            GeneratedQuestionChunk.generated_question_id == proposals[0].id
        )
    )
    assert chunk.chunk_id == corpus.chunks["ready-0.pdf"][1].id
    assert chunk.relevance == RelevanceGrade.SUFFICIENT
    assert chunk.quote == PENALTY
    # The outline marks the zones and the passage is located in its chunk.
    outline = last_tool_result(model.model.seen[1])
    assert "d1:c0 p.1 zone 1" in outline and "zone 2" in outline
    assert "d1:c1" in last_tool_result(model.model.seen[2])


async def test_tools_called_together_run_one_after_the_other(session, client):
    corpus = await build_corpus(session, client)
    job = await _job(session, corpus, per_document=3)
    unit = await _unit(session, job, GenerationPhase.DOCUMENT)
    first = submit("Quanto costa il ritardo?", "L'1 per mille.", ("d1:c1", PENALTY))
    second = submit("Quanto dura il contratto?", "Tre anni.", ("d1:c3", DURATION))
    # One turn with several calls: the agent runs them concurrently, on one session.
    together = AIMessage(
        content="",
        tool_calls=[
            *first.tool_calls,
            *second.tool_calls,
            *tool_call("read_chunk", chunk="d1:c2").tool_calls,
        ],
    )
    model = scripted(together, tool_call("finish"))

    status = await GenerationRunner(session, chat_model=model).run_unit(unit.id)

    assert status == ExecutionStatus.SUCCEEDED
    assert unit.produced == 2
    assert len(await _proposals(session, unit)) == 2


async def test_quote_in_the_wrong_chunk_is_discarded_and_corrected(session, client):
    corpus = await build_corpus(session, client)
    job = await _job(session, corpus, per_document=1)
    unit = await _unit(session, job, GenerationPhase.DOCUMENT)
    question = "Quanto costa ogni giorno di ritardo?"
    model = scripted(
        submit(question, "L'1 per mille.", ("d1:c0", PENALTY)),
        lambda messages: (
            submit(question, "L'1 per mille.", ("d1:c1", PENALTY))
            if "quote_not_in_chunk" in last_tool_result(messages)
            else tool_call("finish")
        ),
        tool_call("finish", summary="s"),
    )

    await GenerationRunner(session, chat_model=model).run_unit(unit.id)

    assert unit.discards == {"quote_not_in_chunk": 1}
    assert unit.produced == 1
    assert "saved" in last_tool_result(model.model.seen[2])


async def test_invented_and_outside_chunks_are_discarded(session, client):
    corpus = await build_corpus(session, client)
    job = await _job(session, corpus, per_document=1)
    unit = await _unit(session, job, GenerationPhase.DOCUMENT)
    model = scripted(
        submit("Chi nomina il referente?", "Il fornitore.", ("d3:c0", REFERENT)),
        submit("Che cosa dice il capitolo nove?", "Niente.", ("d1:c9", "x " * 6)),
        tool_call("read_chunk", chunk="d3:c0"),
        tool_call("finish"),
    )

    await GenerationRunner(session, chat_model=model).run_unit(unit.id)

    # A chunk of another document cannot even be resolved from a document unit.
    assert unit.discards == {"unknown_chunk": 2}
    assert unit.produced == 0
    assert unit.end_reason == "agent_finished"
    assert "unknown chunk d3:c0" in last_tool_result(model.model.seen[3])


async def test_multi_chunk_question_is_supporting(session, client):
    corpus = await build_corpus(session, client)
    job = await _job(session, corpus, per_document=1)
    unit = await _unit(session, job, GenerationPhase.DOCUMENT)
    model = scripted(
        submit(
            "Quali penali e quali orari di assistenza prevede il capitolato?",
            "1 per mille al giorno; assistenza feriale 9-18.",
            ("d1:c1", PENALTY),
            ("d1:c2", SUPPORT),
        ),
        tool_call("finish", summary="s"),
    )

    await GenerationRunner(session, chat_model=model).run_unit(unit.id)

    [proposal] = await _proposals(session, unit)
    assert proposal.kind == GeneratedKind.MULTI
    grades = (
        await session.scalars(
            select(GeneratedQuestionChunk.relevance).where(
                GeneratedQuestionChunk.generated_question_id == proposal.id
            )
        )
    ).all()
    assert set(grades) == {RelevanceGrade.SUPPORTING}


async def test_cross_unit_reads_the_summaries_and_needs_two_documents(session, client):
    corpus = await build_corpus(session, client)
    job = await _job(session, corpus, per_document=1, cross_document=2)
    first = await _unit(session, job, GenerationPhase.DOCUMENT, 0)
    first.summary = "Penali e durata del contratto."
    first.topics = ["penali"]
    first.status = ExecutionStatus.SUCCEEDED
    await session.flush()
    unit = await _unit(session, job, GenerationPhase.CROSS)
    model = scripted(
        submit("Chi nomina il referente?", "Il fornitore.", ("d3:c0", REFERENT)),
        submit(
            "Chi coordina l'assistenza e in che orari è garantita?",
            "Il referente tecnico, dal lunedì al venerdì 9-18.",
            ("d1:c2", SUPPORT),
            ("d3:c1", "Il referente tecnico coordina gli interventi di assistenza"),
        ),
        tool_call("finish"),
    )

    await GenerationRunner(session, chat_model=model).run_unit(unit.id)

    task = model.model.seen[0][-1].content
    assert "d1 | ready-0.pdf" in task and "Penali e durata del contratto." in task
    assert unit.discards == {"single_document": 1}
    [proposal] = await _proposals(session, unit)
    assert proposal.kind == GeneratedKind.CROSS


async def test_resumed_unit_asks_only_for_what_is_left(session, client):
    corpus = await build_corpus(session, client)
    job = await _job(session, corpus, per_document=2)
    unit = await _unit(session, job, GenerationPhase.DOCUMENT)
    saved = "Per quanti anni vale il contratto?"
    first = scripted(
        submit(saved, "Tre anni.", ("d1:c3", DURATION)),
        error=None,
    )
    runner = GenerationRunner(session, chat_model=first)
    # The provider fails after the first question is saved.
    first.model.steps.append(lambda messages: (_ for _ in ()).throw(TimeoutError()))
    with pytest.raises(Exception, match="openai failed"):
        await runner.run_unit(unit.id)
    assert unit.produced == 1

    again = scripted(
        submit("Quanto costa il ritardo?", "L'1 per mille.", ("d1:c1", PENALTY)),
        tool_call("finish", summary="s"),
    )
    await GenerationRunner(session, chat_model=again).run_unit(unit.id)

    task = again.model.seen[0][-1].content
    assert "Write 1 question(s)" in task
    assert saved in task
    assert unit.produced == 2
    assert unit.end_reason == "target_reached"


async def test_step_limit_ends_the_unit_with_what_it_saved(session, client):
    corpus = await build_corpus(session, client)
    job = await _job(session, corpus, per_document=3, max_steps=5)
    unit = await _unit(session, job, GenerationPhase.DOCUMENT)
    model = scripted(
        submit("Per quanti anni vale il contratto?", "Tre anni.", ("d1:c3", DURATION)),
        *[tool_call("read_chunk", chunk="d1:c0") for _ in range(10)],
    )

    status = await GenerationRunner(session, chat_model=model).run_unit(unit.id)

    assert status == ExecutionStatus.SUCCEEDED
    assert unit.end_reason == "max_steps"
    assert unit.produced == 1


async def test_output_error_ends_the_unit(session, client):
    corpus = await build_corpus(session, client)
    job = await _job(session, corpus, per_document=1)
    unit = await _unit(session, job, GenerationPhase.DOCUMENT)
    model = scripted(error=OutputParserException("bad"))

    status = await GenerationRunner(session, chat_model=model).run_unit(unit.id)

    assert status == ExecutionStatus.SUCCEEDED
    assert unit.end_reason == "invalid_output"


async def test_duplicates_of_the_set_are_discarded(session, client):
    corpus = await build_corpus(session, client)
    created = await client.post(
        f"/api/v1/qa-sets/{corpus.qa_set_id}/questions",
        json={"text": "Per quanti anni vale il contratto?"},
    )
    assert created.status_code == 201, created.text
    job = await _job(session, corpus, per_document=1)
    unit = await _unit(session, job, GenerationPhase.DOCUMENT)
    model = scripted(
        submit("Per quanti anni vale il contratto?", "Tre.", ("d1:c3", DURATION)),
        tool_call("finish"),
    )

    await GenerationRunner(session, chat_model=model).run_unit(unit.id)

    assert unit.discards == {"duplicate": 1}


async def test_search_finds_chunks_of_other_documents(session, client):
    corpus = await build_corpus(session, client)
    job = await _job(session, corpus, per_document=0, cross_document=1)
    unit = await _unit(session, job, GenerationPhase.CROSS)
    model = scripted(
        tool_call("search", query="referente assistenza"),
        tool_call("search", query="fatture", docs=["d2"]),
        tool_call("read_document", doc="d2", offset=0, max_chars=200),
        tool_call("finish"),
    )

    await GenerationRunner(session, chat_model=model).run_unit(unit.id)

    found = last_tool_result(model.model.seen[1])
    assert found.splitlines()[0].startswith("d3:c1")
    assert "d2:c0" in last_tool_result(model.model.seen[2])
    window = last_tool_result(model.model.seen[3])
    assert "Le fatture sono pagate" in window and "end of the document" in window


async def test_a_unit_is_traced_with_its_checks(session, client, langfuse, monkeypatch):
    from src.infrastructure.observability import get_tracer

    tracer = get_tracer()
    # The LangChain handler talks to a real client; its nesting is Langfuse's to keep.
    monkeypatch.setattr(tracer, "langchain_callbacks", list)
    corpus = await build_corpus(session, client)
    job = await _job(session, corpus, per_document=1)
    unit = await _unit(session, job, GenerationPhase.DOCUMENT)
    model = scripted(
        submit("Chi?", "Nessuno.", ("d1:c0", "breve")),
        submit("Per quanti anni vale il contratto?", "Tre anni.", ("d1:c3", DURATION)),
        tool_call("finish", summary="s"),
    )

    await GenerationRunner(session, tracer, chat_model=model).run_unit(unit.id)

    [root] = langfuse.named("generate-questions")
    assert root.trace_context == {"trace_id": tracer.trace_id(str(unit.id))}
    assert unit.langfuse_trace_id == tracer.trace_id(str(unit.id))
    assert root.updated("output")["end_reason"] == "target_reached"
    checks = langfuse.named("verify")
    assert [check.parent for check in checks] == ["generate-questions"] * 2
    assert [check.updated("output")["reason"] for check in checks] == [
        "quote_not_in_chunk",
        None,
    ]
    [attributes] = langfuse.propagated
    assert attributes["metadata"]["generation_job_id"] == str(job.id)
    assert attributes["metadata"]["phase"] == "document"
    assert attributes["metadata"]["document"] == "ready-0.pdf"
    assert attributes["metadata"]["prompt_version"] == "1"
    assert attributes["tags"] == ["generation", "phase:document"]
