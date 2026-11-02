from __future__ import annotations

import uuid

import pytest
from src.experiments.models import Execution
from src.experiments.tracing import dataset_item_id, trace_metadata, trace_tags
from src.infrastructure.observability import (
    NULL_TRACER,
    LangfuseTracer,
    build_tracer,
    trace_url,
)
from src.settings import Settings
from tests.tracing_factory import FakeLangfuse


def test_tracing_is_off_without_both_keys() -> None:
    only_public = Settings(langfuse_public_key="pk", langfuse_secret_key=None)
    only_secret = Settings(langfuse_public_key=None, langfuse_secret_key="sk")
    assert build_tracer(only_public) is NULL_TRACER
    assert build_tracer(only_secret) is NULL_TRACER


def test_the_null_tracer_runs_the_block_and_has_no_trace() -> None:
    assert NULL_TRACER.trace_id("seed") is None
    with NULL_TRACER.observe("anything") as observation:
        observation.update(output="ignored")
    assert observation.id is None


def test_the_trace_id_is_derived_from_the_seed() -> None:
    tracer = LangfuseTracer(FakeLangfuse())
    assert tracer.trace_id("execution-1") == tracer.trace_id("execution-1")
    assert tracer.trace_id("execution-1") != tracer.trace_id("execution-2")
    assert len(tracer.trace_id("execution-1")) == 32


def test_a_failing_backend_never_fails_the_observed_code() -> None:
    tracer = LangfuseTracer(FakeLangfuse(fail_observations=True))
    with tracer.observe("root", trace_id="a" * 32) as observation:
        observation.update(output="still runs")
        result = 42
    assert result == 42

    with pytest.raises(ValueError, match="the code's own"), tracer.observe("root"):
        raise ValueError("the code's own")


def test_an_exception_marks_the_observation_and_goes_through() -> None:
    client = FakeLangfuse()
    tracer = LangfuseTracer(client)
    with (
        pytest.raises(RuntimeError),
        tracer.observe("root", trace_id="b" * 32),
        tracer.observe("child"),
    ):
        raise RuntimeError("provider down")

    root, child = client.observations
    assert root.trace_context == {"trace_id": "b" * 32}
    assert child.parent == "root"
    assert child.updated("level") == "ERROR"
    assert child.updated("status_message") == "provider down"
    assert root.updated("level") == "ERROR"


def test_a_trace_links_to_the_langfuse_ui() -> None:
    assert trace_url(None, "https://cloud.langfuse.com") is None
    assert (
        trace_url("abc", "https://langfuse.local/")
        == "https://langfuse.local/trace/abc"
    )


def test_a_question_has_one_item_per_snapshot() -> None:
    question = uuid.uuid4()
    first, second = uuid.uuid4(), uuid.uuid4()
    assert dataset_item_id(first, question) == dataset_item_id(first, question)
    assert dataset_item_id(first, question) != dataset_item_id(second, question)


def test_the_trace_metadata_names_the_configuration_that_ran() -> None:
    variant_id = uuid.uuid4()
    execution = Execution(
        id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        variant_id=variant_id,
        question_id=uuid.uuid4(),
        repetition=1,
    )
    snapshot = {
        "experiment": {"id": "e-1", "name": "prompts", "retrieval_scope": "cited"},
        "qa_set_snapshot": {"id": "q-1"},
        "corpus_snapshot": {"id": "c-1"},
        "variants": [
            {
                "id": str(variant_id),
                "name": "dense top-5 · rag_simple",
                "index_build": {"id": "i-1", "chunking_configuration_id": "cc-1"},
                "embedding_profile": {"name": "openai small"},
                "vector_store_profile": {"name": "chroma cosine"},
                "retrieval_profile": {"name": "dense top-5"},
                "answer_profile": {
                    "name": "rag_simple concise",
                    "component": "rag_simple@1",
                    "params": {"model": "gpt-test", "system_prompt": "x" * 500},
                },
            }
        ],
    }

    metadata = trace_metadata(
        snapshot, execution, parsing_profile="pypdf", chunking_profile="recursive 800"
    )

    assert metadata["variant"] == "dense top-5 · rag_simple"
    assert metadata["parsing_profile"] == "pypdf"
    assert metadata["chunking_profile"] == "recursive 800"
    assert metadata["chunking_configuration_id"] == "cc-1"
    assert metadata["answer_profile"] == "rag_simple concise"
    assert metadata["answer_system"] == "rag_simple@1"
    assert metadata["model"] == "gpt-test"
    assert metadata["retrieval_scope"] == "cited"
    assert metadata["execution_id"] == str(execution.id)
    assert metadata["repetition"] == "1"
    # Only short strings: the prompt itself stays in the run's snapshot.
    assert all(isinstance(value, str) for value in metadata.values())
    assert "system_prompt" not in metadata
    assert trace_tags(snapshot, execution) == [
        "experiment:prompts",
        "variant:dense top-5 · rag_simple",
    ]
