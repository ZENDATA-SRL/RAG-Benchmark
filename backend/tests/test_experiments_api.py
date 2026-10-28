from __future__ import annotations

import dataclasses
import uuid

import pytest
from sqlalchemy import func, select
from src.artifacts.models import Chunk, ChunkResult
from src.experiments.evaluation import ExecutionRunner
from src.experiments.models import (
    Evaluation,
    Execution,
    MetricDefinition,
    RetrievalCall,
    RetrievalHit,
)
from src.experiments.repository import ExecutionRepository
from src.experiments.service import RunService
from src.indexes.models import IndexBuild
from src.infrastructure.database.enums import ArtifactStatus, ExecutionStatus
from src.retrieval.exceptions import IndexBuildNotReadyError
from src.retrieval.service import RetrievalService
from tests.pipeline_factory import (
    Scenario,
    build_scenario,
    make_configuration,
    materialise,
)
from tests.retrieval_factory import indexed_build

pytestmark = pytest.mark.integration

EXPERIMENTS = "/api/v1/experiments"
QA_SETS = "/api/v1/qa-sets"


@dataclasses.dataclass
class World:
    """Three indexed documents, a QA set over them and a frozen snapshot of it.

    Four questions: one per gold document, an unanswerable one and one whose gold document
    is in the corpus but not in the snapshot the index was built on.
    """

    scenario: Scenario
    build: IndexBuild
    qa_snapshot_id: str
    question_ids: dict[str, str]
    profile_small: str
    profile_large: str


async def _chunk_text(session, document) -> str:
    stmt = (
        select(Chunk.text)
        .join(ChunkResult, ChunkResult.id == Chunk.chunk_result_id)
        .where(ChunkResult.document_id == document.id)
        .order_by(Chunk.ordinal)
    )
    return (await session.scalars(stmt)).first()


async def _profile(client, top_k: int) -> str:
    response = await client.post("/api/v1/retrieval-profiles", json={"top_k": top_k})
    assert response.status_code == 201, response.text
    return response.json()["profile"]["id"]


@pytest.fixture
async def world(client, session, fake_engine, chroma_client) -> World:
    scenario = await build_scenario(session, ready=3, missing=1, chunks_per_document=2)
    build = await indexed_build(session, scenario, chroma_client)
    first = await _chunk_text(session, scenario.ready[0])
    second = await _chunk_text(session, scenario.ready[1])

    created = await client.post(
        QA_SETS, json={"name": "qa", "origin_corpus_id": scenario.corpus_id}
    )
    qa_set_id = created.json()["id"]
    csv = (
        "question,gold_files,tags,answerable\n"
        f'"{first}",ready-0.pdf,alpha,true\n'
        f'"{second}",ready-1.pdf,beta,true\n'
        "Nobody knows?,,alpha,false\n"
        "Gold outside the snapshot?,missing-0.pdf,beta,true\n"
    )
    imported = await client.post(
        f"{QA_SETS}/{qa_set_id}/import", files={"file": ("q.csv", csv.encode())}
    )
    assert imported.status_code == 200, imported.text
    summary = imported.json()
    assert len(summary["imported"]) == 4, summary
    frozen = await client.post(f"{QA_SETS}/{qa_set_id}/snapshots", json={})
    return World(
        scenario=scenario,
        build=build,
        qa_snapshot_id=frozen.json()["snapshot"]["id"],
        question_ids={
            item["text"]: item["question_id"] for item in summary["imported"]
        },
        profile_small=await _profile(client, 1),
        profile_large=await _profile(client, 6),
    )


def _body(world: World, **overrides) -> dict:
    body = {
        "name": "retrieval",
        "type": "retrieval",
        "corpus_snapshot_id": str(world.build.corpus_snapshot_id),
        "qa_set_snapshot_id": world.qa_snapshot_id,
        "uncovered_policy": "exclude",
        "variants": [
            {
                "index_build_id": str(world.build.id),
                "retrieval_profile_id": world.profile_small,
                "is_baseline": True,
            },
            {
                "index_build_id": str(world.build.id),
                "retrieval_profile_id": world.profile_large,
            },
        ],
    }
    body.update(overrides)
    return body


async def _create(client, world: World, **overrides) -> dict:
    response = await client.post(EXPERIMENTS, json=_body(world, **overrides))
    assert response.status_code == 201, response.text
    return response.json()


def _retrieval(name: str) -> str:
    """The retrieval profile a derived variant name ends with, such as `dense top-1`."""
    return name.rsplit(" · ", 1)[-1]


def _variants(results: dict) -> list[dict]:
    """The variants of every chunking configuration group, in order."""
    return [variant for group in results["groups"] for variant in group["variants"]]


async def _execute_run(session, run_id: str) -> None:
    """Do in-process what the workflow does: run every unfinished execution, then close."""
    executions = (
        await session.scalars(
            select(Execution).where(
                Execution.run_id == uuid.UUID(run_id),
                Execution.status != ExecutionStatus.SUCCEEDED,
            )
        )
    ).all()
    for execution in executions:
        await ExecutionRunner(session).run(execution.id)
    await RunService(session).finish_run(uuid.UUID(run_id))


# -- guards -------------------------------------------------------------------------------


async def test_variants_on_another_snapshot_are_refused(
    client, session, world, chroma_client
) -> None:
    narrower = await indexed_build(
        session, world.scenario, chroma_client, documents=world.scenario.ready[:2]
    )
    body = _body(world)
    body["variants"][1]["index_build_id"] = str(narrower.id)

    response = await client.post(EXPERIMENTS, json=body)

    assert response.status_code == 422
    error = response.json()
    assert error["code"] == "variants_outside_snapshot"
    assert [_retrieval(item["name"]) for item in error["details"]["variants"]] == [
        "dense top-6"
    ]


async def test_uncovered_questions_need_an_explicit_choice(client, world) -> None:
    body = _body(world)
    del body["uncovered_policy"]

    response = await client.post(EXPERIMENTS, json=body)

    assert response.status_code == 422
    error = response.json()
    assert error["code"] == "gold_coverage_choice_required"
    uncovered = error["details"]["uncovered_questions"]
    assert [item["text"] for item in uncovered] == ["Gold outside the snapshot?"]
    assert uncovered[0]["missing_documents"][0]["filename"] == "missing-0.pdf"


async def test_the_coverage_check_lists_the_same_questions(client, world) -> None:
    response = await client.get(
        f"{EXPERIMENTS}/coverage",
        params={
            "corpus_snapshot_id": str(world.build.corpus_snapshot_id),
            "qa_set_snapshot_id": world.qa_snapshot_id,
        },
    )

    body = response.json()
    assert body["question_count"] == 4
    assert body["uncovered_count"] == 1


async def test_a_second_baseline_is_refused(client, world) -> None:
    body = _body(world)
    body["variants"][1]["is_baseline"] = True

    response = await client.post(EXPERIMENTS, json=body)

    assert response.status_code == 422
    assert response.json()["code"] == "multiple_baselines"


async def test_the_first_variant_is_the_baseline_when_none_is_marked(
    client, world
) -> None:
    body = _body(world)
    body["variants"][0]["is_baseline"] = False

    created = await client.post(EXPERIMENTS, json=body)

    baselines = [
        _retrieval(item["name"])
        for item in created.json()["variants"]
        if item["is_baseline"]
    ]
    assert baselines == ["dense top-1"]


async def test_only_retrieval_experiments_exist_for_now(client, world) -> None:
    response = await client.post(EXPERIMENTS, json=_body(world, type="qa"))

    assert response.status_code == 422
    assert response.json()["code"] == "unsupported_operation"


async def test_the_detail_shows_variants_and_coverage(client, world) -> None:
    created = await _create(client, world)

    detail = (await client.get(f"{EXPERIMENTS}/{created['id']}")).json()

    assert detail["uncovered_policy"] == "exclude"
    configuration = world.scenario.configuration.name
    # Named after what each variant searches and how, not after the snapshot they share.
    assert [item["name"] for item in detail["variants"]] == [
        f"{configuration} · openai@1 text-embedding-3-small · chromadb@1 cosine"
        f" · dense top-{top_k}"
        for top_k in (1, 6)
    ]
    assert detail["variants"][0]["top_k"] == 1
    assert detail["coverage"]["uncovered_count"] == 1
    listing = (await client.get(EXPERIMENTS)).json()
    assert listing["items"][0]["variant_count"] == 2


async def test_an_experiment_names_its_corpus_and_qa_set(client, world) -> None:
    created = await _create(client, world)

    detail = (await client.get(f"{EXPERIMENTS}/{created['id']}")).json()
    listed = (await client.get(EXPERIMENTS)).json()["items"][0]

    for item in (detail, listed):
        assert item["corpus_id"] == str(world.scenario.corpus_id)
        assert item["corpus_name"]
        assert item["corpus_snapshot_label"]
        assert item["qa_set_name"] == "qa"
        assert item["qa_set_id"]
        assert item["qa_set_snapshot_label"]


# -- run launch ---------------------------------------------------------------------------


async def test_a_run_copies_the_configuration_and_creates_every_execution(
    client, world, fake_workflows
) -> None:
    experiment = await _create(client, world, repetitions=2)

    response = await client.post(
        f"{EXPERIMENTS}/{experiment['id']}/runs", json={"concurrency": 3}
    )

    assert response.status_code == 202, response.text
    run = response.json()
    # 4 questions x 2 variants x 2 repetitions
    assert run["progress"] == {"total": 16, "succeeded": 0, "failed": 0, "pending": 16}
    launch = fake_workflows.started[0]
    assert launch.workflow == "RunExperimentWorkflow"
    assert launch.workflow_id == f"run-experiment-{run['id']}"
    assert launch.arg == {"run_id": run["id"], "concurrency": 3}
    detail = (
        await client.get(f"{EXPERIMENTS}/{experiment['id']}/runs/{run['id']}")
    ).json()
    snapshot = detail["config_snapshot"]
    assert snapshot["corpus_snapshot"]["id"] == experiment["corpus_snapshot_id"]
    assert [item["retrieval_profile"]["top_k"] for item in snapshot["variants"]] == [
        1,
        6,
    ]
    assert snapshot["variants"][0]["embedding_profile"]["params"] is not None


async def test_a_run_needs_every_index_build_ready(client, session, world) -> None:
    experiment = await _create(client, world)
    build = await session.get(IndexBuild, world.build.id)
    build.status = ArtifactStatus.RUNNING
    await session.flush()

    response = await client.post(f"{EXPERIMENTS}/{experiment['id']}/runs", json={})

    assert response.status_code == 409
    assert response.json()["code"] == "index_build_not_ready"


async def test_a_run_can_be_cancelled_once(client, world, fake_workflows) -> None:
    experiment = await _create(client, world)
    run = (await client.post(f"{EXPERIMENTS}/{experiment['id']}/runs", json={})).json()
    url = f"{EXPERIMENTS}/{experiment['id']}/runs/{run['id']}/cancel"

    cancelled = await client.post(url)
    again = await client.post(url)

    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "failed"
    assert cancelled.json()["error"] == "cancelled"
    assert fake_workflows.cancelled == [f"run-experiment-{run['id']}"]
    assert again.status_code == 409
    assert again.json()["code"] == "run_not_cancellable"


# -- execution, metrics, results ----------------------------------------------------------


async def test_results_count_every_question_and_name_the_snapshot(
    client, session, world
) -> None:
    experiment = await _create(client, world)
    run = (await client.post(f"{EXPERIMENTS}/{experiment['id']}/runs", json={})).json()
    await _execute_run(session, run["id"])

    response = await client.get(
        f"{EXPERIMENTS}/{experiment['id']}/runs/{run['id']}/results"
    )

    assert response.status_code == 200, response.text
    results = response.json()
    assert results["status"] == "succeeded"
    assert results["corpus_snapshot"]["id"] == experiment["corpus_snapshot_id"]
    assert results["corpus_snapshot"]["document_count"] == 3
    assert results["question_count"] == 4
    for variant in _variants(results):
        for metric in variant["metrics"]:
            if metric["level"] == "chunk" or metric["key"] == "first_relevant_rank":
                continue
            # 2 questions count, 2 are excluded: together they are the snapshot.
            assert (
                metric["n_effective"] + metric["n_excluded"]
                == results["question_count"]
            )
            assert metric["n_effective"] == 2
            assert metric["n_excluded"] == 2
    by_name = {_retrieval(variant["name"]): variant for variant in _variants(results)}
    large = {metric["key"]: metric for metric in by_name["dense top-6"]["metrics"]}
    # The query is the text of a chunk of the gold document, so it comes back first.
    assert large["mrr"]["mean"] == 1.0
    assert large["recall@5"]["mean"] == 1.0
    assert large["hit_rate@1"]["mean"] == 1.0
    assert by_name["dense top-1"]["is_baseline"] is True


async def test_tag_slices_aggregate_over_the_questions_with_that_tag(
    client, session, world
) -> None:
    experiment = await _create(client, world)
    run = (await client.post(f"{EXPERIMENTS}/{experiment['id']}/runs", json={})).json()
    await _execute_run(session, run["id"])

    response = await client.get(
        f"{EXPERIMENTS}/{experiment['id']}/runs/{run['id']}/results",
        params={"tag": "alpha"},
    )

    metric = {m["key"]: m for m in _variants(response.json())[0]["metrics"]}["recall@5"]
    # alpha: the answerable question (counts) and the unanswerable one (excluded).
    assert (metric["n_effective"], metric["n_excluded"]) == (1, 1)


async def test_excluded_executions_carry_their_reason(client, session, world) -> None:
    experiment = await _create(client, world)
    run = (await client.post(f"{EXPERIMENTS}/{experiment['id']}/runs", json={})).json()
    await _execute_run(session, run["id"])

    rows = (
        await session.execute(
            select(MetricDefinition.level, Evaluation.exclusion_reason, func.count())
            .join(Execution, Execution.id == Evaluation.execution_id)
            .join(
                MetricDefinition,
                MetricDefinition.id == Evaluation.metric_definition_id,
            )
            .where(
                Execution.run_id == uuid.UUID(run["id"]), Evaluation.excluded.is_(True)
            )
            .group_by(MetricDefinition.level, Evaluation.exclusion_reason)
        )
    ).all()
    reasons = {(level.value, reason): count for level, reason, count in rows}

    # Per variant and metric, 2 variants. Documents, 14 metrics: 1 unanswerable and 1
    # uncovered question. Chunks, 22 metrics: the unanswerable one, and the other three
    # because nobody reviewed their evidence, which comes before the snapshot check.
    assert reasons == {
        ("document", "not_answerable"): 28,
        ("document", "gold_document_not_in_snapshot"): 28,
        ("chunk", "not_answerable"): 44,
        ("chunk", "evidence_not_reviewed"): 132,
    }


async def test_the_drilldown_shows_each_variant_hits_and_why_they_count(
    client, session, world
) -> None:
    experiment = await _create(client, world)
    run = (await client.post(f"{EXPERIMENTS}/{experiment['id']}/runs", json={})).json()
    await _execute_run(session, run["id"])
    first_question = next(
        qid
        for text, qid in world.question_ids.items()
        if text.startswith("chunk 0 of ready-0")
    )

    response = await client.get(
        f"{EXPERIMENTS}/{experiment['id']}/runs/{run['id']}/questions/{first_question}"
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert [gold["filename"] for gold in body["gold_documents"]] == ["ready-0.pdf"]
    by_name = {_retrieval(variant["name"]): variant for variant in body["variants"]}
    assert len(by_name["dense top-1"]["executions"][0]["hits"]) == 1
    large_hits = by_name["dense top-6"]["executions"][0]["hits"]
    assert len(large_hits) == 6
    assert large_hits[0]["filename"] == "ready-0.pdf"
    assert large_hits[0]["relevant_document"] is True
    assert {
        hit["relevant_document"]
        for hit in large_hits
        if hit["filename"] != "ready-0.pdf"
    } == {False}


async def test_the_question_table_lists_the_outcome_of_each_variant(
    client, session, world
) -> None:
    experiment = await _create(client, world)
    run = (await client.post(f"{EXPERIMENTS}/{experiment['id']}/runs", json={})).json()
    await _execute_run(session, run["id"])

    response = await client.get(
        f"{EXPERIMENTS}/{experiment['id']}/runs/{run['id']}/questions"
    )

    page = response.json()
    assert page["total"] == 4
    by_text = {row["text"]: row for row in page["items"]}
    unknowable = by_text["Nobody knows?"]
    assert {outcome["excluded_reason"] for outcome in unknowable["outcomes"]} == {
        "not_answerable"
    }
    answered = next(
        row for text, row in by_text.items() if text.startswith("chunk 0 of ready-0")
    )
    assert [outcome["first_relevant_rank"] for outcome in answered["outcomes"]] == [
        1.0,
        1.0,
    ]


async def test_a_question_outside_the_run_is_not_found(client, session, world) -> None:
    experiment = await _create(client, world)
    run = (await client.post(f"{EXPERIMENTS}/{experiment['id']}/runs", json={})).json()

    response = await client.get(
        f"{EXPERIMENTS}/{experiment['id']}/runs/{run['id']}/questions/{uuid.uuid4()}"
    )

    assert response.status_code == 404
    assert response.json()["code"] == "question_not_in_run"


async def test_results_download_as_csv(client, session, world) -> None:
    experiment = await _create(client, world)
    run = (await client.post(f"{EXPERIMENTS}/{experiment['id']}/runs", json={})).json()
    await _execute_run(session, run["id"])

    response = await client.get(
        f"{EXPERIMENTS}/{experiment['id']}/runs/{run['id']}/results.csv"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    lines = response.text.strip().splitlines()
    assert lines[0].startswith(
        "chunking_configuration_id,variant,is_baseline,level,metric,mean"
    )
    assert len(lines) == 1 + 2 * (14 + 22)
    assert ",document,recall@5," in response.text
    assert ",chunk,chunk_recall@5," in response.text
    assert world.qa_snapshot_id in lines[1]


# -- failures and resume ------------------------------------------------------------------


async def test_a_failed_execution_is_excluded_and_a_resume_redoes_only_it(
    client, session, world, fake_workflows
) -> None:
    experiment = await _create(client, world)
    run = (await client.post(f"{EXPERIMENTS}/{experiment['id']}/runs", json={})).json()
    run_id = uuid.UUID(run["id"])
    broken = (
        await session.scalars(
            select(Execution).where(Execution.run_id == run_id).order_by(Execution.id)
        )
    ).first()
    await ExecutionRunner(session).fail(broken.id, "boom")
    await _execute_run(session, run["id"])
    # `_execute_run` retried the failed one as well: break it again, as if it kept failing.
    await ExecutionRunner(session).fail(broken.id, "boom")
    await RunService(session).finish_run(run_id)
    fake_workflows._running.clear()

    done = (
        await client.get(f"{EXPERIMENTS}/{experiment['id']}/runs/{run['id']}")
    ).json()
    assert done["status"] == "succeeded"
    assert done["progress"]["failed"] == 1

    resumed = await client.post(
        f"{EXPERIMENTS}/{experiment['id']}/runs/{run['id']}/resume"
    )

    assert resumed.status_code == 202, resumed.text
    assert resumed.json()["status"] == "pending"
    assert fake_workflows.started[-1].workflow_id == f"run-experiment-{run['id']}"
    assert await _unfinished(session, run_id) == [broken.id]


async def _unfinished(session, run_id: uuid.UUID) -> list[uuid.UUID]:
    """The executions a relaunch would pick up, through the query the worker uses."""
    repository = ExecutionRepository(session)
    variants = (
        await session.scalars(
            select(Execution.variant_id).where(Execution.run_id == run_id).distinct()
        )
    ).all()
    found: list[uuid.UUID] = []
    for variant_id in variants:
        found += await repository.unfinished_ids(
            run_id, variant_id, after_id=None, limit=100
        )
    return found


async def test_a_finished_run_without_failures_cannot_be_resumed(
    client, session, world
) -> None:
    experiment = await _create(client, world)
    run = (await client.post(f"{EXPERIMENTS}/{experiment['id']}/runs", json={})).json()
    await _execute_run(session, run["id"])

    response = await client.post(
        f"{EXPERIMENTS}/{experiment['id']}/runs/{run['id']}/resume"
    )

    assert response.status_code == 409
    assert response.json()["code"] == "run_not_resumable"


async def test_a_rerun_of_a_succeeded_execution_changes_nothing(
    client, session, world
) -> None:
    experiment = await _create(client, world)
    run = (await client.post(f"{EXPERIMENTS}/{experiment['id']}/runs", json={})).json()
    await _execute_run(session, run["id"])
    calls_before = await session.scalar(select(func.count()).select_from(RetrievalCall))
    execution = (
        await session.scalars(
            select(Execution).where(Execution.run_id == uuid.UUID(run["id"]))
        )
    ).first()

    outcome = await ExecutionRunner(session).run(execution.id)

    assert outcome.status == ExecutionStatus.SUCCEEDED
    assert (
        await session.scalar(select(func.count()).select_from(RetrievalCall))
        == calls_before
    )


async def test_a_question_that_cannot_be_retrieved_fails_alone(
    client, session, world, monkeypatch
) -> None:
    experiment = await _create(client, world)
    run = (await client.post(f"{EXPERIMENTS}/{experiment['id']}/runs", json={})).json()
    original = RetrievalService.search

    async def flaky(self, **kwargs):
        if kwargs["query"].startswith("Nobody"):
            raise IndexBuildNotReadyError(kwargs["index_build_id"], "running")
        return await original(self, **kwargs)

    monkeypatch.setattr(RetrievalService, "search", flaky)

    await _execute_run(session, run["id"])

    done = (
        await client.get(f"{EXPERIMENTS}/{experiment['id']}/runs/{run['id']}")
    ).json()
    assert done["progress"] == {"total": 8, "succeeded": 6, "failed": 2, "pending": 0}
    failed = (
        await session.scalars(
            select(Execution).where(Execution.status == ExecutionStatus.FAILED)
        )
    ).all()
    assert all("not ready" in (execution.error or "") for execution in failed)


# -- retrieval tracking -------------------------------------------------------------------


async def test_a_retrieve_call_with_an_execution_records_its_hits(
    client, session, world
) -> None:
    experiment = await _create(client, world)
    run = (await client.post(f"{EXPERIMENTS}/{experiment['id']}/runs", json={})).json()
    execution = (
        await session.scalars(
            select(Execution).where(Execution.run_id == uuid.UUID(run["id"]))
        )
    ).first()

    for _ in range(2):
        response = await client.post(
            "/api/v1/retrieve",
            json={
                "index_build_id": str(world.build.id),
                "retrieval_profile_id": world.profile_large,
                "query": "something",
                "execution_id": str(execution.id),
            },
        )
        assert response.status_code == 200, response.text

    calls = (
        await session.scalars(
            select(RetrievalCall)
            .where(RetrievalCall.execution_id == execution.id)
            .order_by(RetrievalCall.call_index)
        )
    ).all()
    assert [call.call_index for call in calls] == [1, 2]
    assert calls[0].query_text == "something"
    hits = await session.scalar(
        select(func.count())
        .select_from(RetrievalHit)
        .where(RetrievalHit.retrieval_call_id == calls[0].id)
    )
    assert hits == 6


async def test_a_retrieve_call_for_an_unknown_execution_is_refused(
    client, world
) -> None:
    response = await client.post(
        "/api/v1/retrieve",
        json={
            "index_build_id": str(world.build.id),
            "retrieval_profile_id": world.profile_large,
            "query": "something",
            "execution_id": str(uuid.uuid4()),
        },
    )

    assert response.status_code == 404
    assert response.json()["code"] == "execution_not_found"


async def test_the_worker_activities_drive_a_run_to_the_same_results(
    client, session, world, monkeypatch
) -> None:
    """The real activities, on the test transaction, in the order the workflow calls them."""
    import contextlib

    from temporal.activities import experiments as activities

    @contextlib.asynccontextmanager
    async def test_session():
        yield session
        await session.flush()

    monkeypatch.setattr(activities, "activity_session", test_session)
    experiment = await _create(client, world)
    run = (await client.post(f"{EXPERIMENTS}/{experiment['id']}/runs", json={})).json()

    resolved = await activities.open_experiment_run(run["id"])
    for variant_id in resolved.variant_ids:
        cursor = None
        while page := await activities.list_unfinished_executions(
            run["id"], variant_id, cursor, 3
        ):
            for execution_id in page:
                assert await activities.retrieve_question(execution_id) == "succeeded"
            cursor = page[-1]
            await activities.record_run_progress(run["id"])
    await activities.finish_experiment_run(run["id"])

    done = (
        await client.get(f"{EXPERIMENTS}/{experiment['id']}/runs/{run['id']}")
    ).json()
    assert done["status"] == "succeeded"
    assert done["progress"] == {"total": 8, "succeeded": 8, "failed": 0, "pending": 0}
    results = (
        await client.get(f"{EXPERIMENTS}/{experiment['id']}/runs/{run['id']}/results")
    ).json()
    mrr = {m["key"]: m for m in _variants(results)[0]["metrics"]}["mrr"]
    assert (mrr["mean"], mrr["n_effective"], mrr["n_excluded"]) == (1.0, 2, 2)
    # Chunk metrics are scored in the same pass, and the run records the evidence used.
    chunk_mrr = {m["key"]: m for m in _variants(results)[0]["metrics"]}["chunk_mrr"]
    assert chunk_mrr["excluded_reasons"] == {
        "not_answerable": 1,
        "evidence_not_reviewed": 3,
    }
    assert results["chunk_gold"]["hash"]


# -- chunk level --------------------------------------------------------------------------

QUESTIONS = "/api/v1/questions"


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


def _question(world: World, prefix: str) -> str:
    return next(
        qid for text, qid in world.question_ids.items() if text.startswith(prefix)
    )


async def _evidence(client, world: World, question_id: str, status: str, chunks=()):
    response = await client.put(
        f"{QUESTIONS}/{question_id}/evidence",
        json={
            "chunking_configuration_id": str(world.build.chunking_configuration_id),
            "status": status,
            "annotator": "anna",
            "chunks": [
                {"chunk_id": str(chunk.id), "relevance": relevance}
                for chunk, relevance in chunks
            ],
        },
    )
    assert response.status_code == 200, response.text


async def _annotate(client, session, world: World) -> None:
    """The question on ready-0 answered by its first chunk; the one on ready-1 not found."""
    first = await _chunks(
        session, world.scenario.ready[0], world.build.chunking_configuration_id
    )
    await _evidence(
        client,
        world,
        _question(world, "chunk 0 of ready-0"),
        "confirmed",
        [(first[0], "sufficient"), (first[1], "supporting")],
    )
    await _evidence(client, world, _question(world, "chunk 0 of ready-1"), "not_found")


def _metrics(results: dict, variant: str) -> dict[str, dict]:
    chosen = next(
        item for item in _variants(results) if _retrieval(item["name"]) == variant
    )
    return {metric["key"]: metric for metric in chosen["metrics"]}


async def _calls(session, run_id: str) -> int:
    stmt = (
        select(func.count())
        .select_from(RetrievalCall)
        .join(Execution, Execution.id == RetrievalCall.execution_id)
        .where(Execution.run_id == uuid.UUID(run_id))
    )
    return await session.scalar(stmt)


async def test_a_run_scored_before_annotation_gains_chunk_metrics_when_reevaluated(
    client, session, world
) -> None:
    experiment = await _create(client, world)
    base = f"{EXPERIMENTS}/{experiment['id']}/runs"
    run = (await client.post(base, json={})).json()
    await _execute_run(session, run["id"])
    before = (await client.get(f"{base}/{run['id']}/results")).json()
    calls = await _calls(session, run["id"])

    chunk_recall = _metrics(before, "dense top-6")["chunk_recall@5"]
    assert (chunk_recall["n_effective"], chunk_recall["excluded_reasons"]) == (
        0,
        {"not_answerable": 1, "evidence_not_reviewed": 3},
    )
    assert before["groups"][0]["evidence_coverage"]["not_reviewed"] == 3
    assert before["groups"][0]["recall_ceiling"] is None

    await _annotate(client, session, world)
    evaluated = await client.post(f"{base}/{run['id']}/evaluate")
    assert evaluated.status_code == 200, evaluated.text
    after = (await client.get(f"{base}/{run['id']}/results")).json()

    large = _metrics(after, "dense top-6")
    # The query is the text of the sufficient chunk, so it comes back first.
    assert (large["chunk_mrr"]["mean"], large["chunk_mrr"]["n_effective"]) == (1.0, 1)
    # The question with no evidence in this configuration is excluded, never a zero.
    assert large["chunk_recall@5"]["excluded_reasons"] == {
        "not_answerable": 1,
        "evidence_not_found": 1,
        "evidence_not_reviewed": 1,
    }
    assert large["chunk_sufficient_hit@1"]["mean"] == 1.0
    assert large["chunk_mrr"]["level"] == "chunk"
    group = after["groups"][0]
    assert group["evidence_coverage"] == {
        "answerable": 3,
        "confirmed": 1,
        "not_found": 1,
        "to_review": 0,
        "not_reviewed": 1,
    }
    assert group["recall_ceiling"] == 0.5
    assert after["chunk_gold"]["hash"] != before["chunk_gold"]["hash"]
    # Re-scoring reads the stored hits: documents unchanged, no new retrieval.
    for variant in ("dense top-1", "dense top-6"):
        for key, metric in _metrics(before, variant).items():
            if metric["level"] == "document":
                assert _metrics(after, variant)[key] == metric
    assert await _calls(session, run["id"]) == calls


async def test_reevaluating_twice_gives_the_same_numbers_and_fingerprint(
    client, session, world
) -> None:
    experiment = await _create(client, world)
    base = f"{EXPERIMENTS}/{experiment['id']}/runs"
    run = (await client.post(base, json={})).json()
    await _execute_run(session, run["id"])
    await _annotate(client, session, world)

    first = (await client.post(f"{base}/{run['id']}/evaluate")).json()
    once = (await client.get(f"{base}/{run['id']}/results")).json()
    second = (await client.post(f"{base}/{run['id']}/evaluate")).json()
    twice = (await client.get(f"{base}/{run['id']}/results")).json()

    assert (
        first["config_snapshot"]["chunk_gold"]["hash"]
        == second["config_snapshot"]["chunk_gold"]["hash"]
    )
    assert [link["status"] for link in second["config_snapshot"]["chunk_gold"]["links"]]
    assert once["groups"] == twice["groups"]


async def test_a_run_in_progress_is_not_reevaluated(client, world) -> None:
    experiment = await _create(client, world)
    base = f"{EXPERIMENTS}/{experiment['id']}/runs"
    run = (await client.post(base, json={})).json()

    response = await client.post(f"{base}/{run['id']}/evaluate")

    assert response.status_code == 409
    assert response.json()["code"] == "run_in_progress"


async def test_repetitions_are_averaged_per_question_before_the_statistics(
    client, session, world
) -> None:
    experiment = await _create(client, world, repetitions=3)
    base = f"{EXPERIMENTS}/{experiment['id']}/runs"
    run = (await client.post(base, json={})).json()
    await _execute_run(session, run["id"])

    results = (await client.get(f"{base}/{run['id']}/results")).json()

    recall = _metrics(results, "dense top-6")["recall@5"]
    # Twelve executions per variant, but four questions: two count and two do not.
    assert (recall["n_effective"], recall["n_excluded"]) == (2, 2)
    assert recall["excluded_reasons"] == {
        "not_answerable": 1,
        "gold_document_not_in_snapshot": 1,
    }


async def test_variants_on_two_chunking_configurations_are_two_groups(
    client, session, world, chroma_client
) -> None:
    _, other = await make_configuration(session, chunk_size=300)
    for document in world.scenario.ready:
        await materialise(
            session, document, world.scenario.parsing_profile, other, chunk_count=2
        )
    other_build = await indexed_build(
        session,
        dataclasses.replace(world.scenario, configuration=other),
        chroma_client,
    )
    body_variants = [
        {
            "index_build_id": str(other_build.id),
            "retrieval_profile_id": world.profile_large,
        },
        {
            "index_build_id": str(world.build.id),
            "retrieval_profile_id": world.profile_large,
            "is_baseline": True,
        },
    ]
    experiment = await _create(client, world, variants=body_variants)
    base = f"{EXPERIMENTS}/{experiment['id']}/runs"
    run = (await client.post(base, json={})).json()

    results = (await client.get(f"{base}/{run['id']}/results")).json()

    groups = {group["chunking_configuration_id"]: group for group in results["groups"]}
    assert {
        configuration: [
            variant["name"].split(" · ")[0] for variant in group["variants"]
        ]
        for configuration, group in groups.items()
    } == {
        str(other.id): [other.name],
        str(world.build.chunking_configuration_id): [world.scenario.configuration.name],
    }
    assert groups[str(other.id)]["chunking"] == "recursive@1 300/50"
    cross = results["cross_group_metrics"]
    assert "recall@5" in cross["keys"]
    assert not any(key.startswith("chunk_") for key in cross["keys"])
    assert "chunking configuration" in cross["reason"]


async def test_the_drilldown_marks_evidence_chunks_and_lists_those_not_retrieved(
    client, session, world
) -> None:
    experiment = await _create(client, world)
    base = f"{EXPERIMENTS}/{experiment['id']}/runs"
    run = (await client.post(base, json={})).json()
    await _execute_run(session, run["id"])
    await _annotate(client, session, world)
    await client.post(f"{base}/{run['id']}/evaluate")
    question_id = _question(world, "chunk 0 of ready-0")

    body = (await client.get(f"{base}/{run['id']}/questions/{question_id}")).json()

    assert body["qa_set_id"]
    by_name = {_retrieval(variant["name"]): variant for variant in body["variants"]}
    small = by_name["dense top-1"]
    assert small["evidence_status"] == "confirmed"
    [hit] = small["executions"][0]["hits"]
    assert (hit["relevant_chunk"], hit["relevance"]) == (True, "sufficient")
    # top-1 retrieves the sufficient chunk only: the supporting one is listed as missed.
    assert {(c["relevance"], c["retrieved"]) for c in small["gold_chunks"]} == {
        ("sufficient", True),
        ("supporting", False),
    }
    large_hits = by_name["dense top-6"]["executions"][0]["hits"]
    assert large_hits[0]["relevant_chunk"] is True

    rows = (await client.get(f"{base}/{run['id']}/questions")).json()["items"]
    unanswerable = next(row for row in rows if row["text"] == "Nobody knows?")
    assert unanswerable["outcomes"][0]["chunk_excluded_reason"] == "not_answerable"
    answered = next(row for row in rows if row["question_id"] == question_id)
    assert answered["outcomes"][0]["chunk_first_relevant_rank"] == 1.0
