from __future__ import annotations

from src.pipelines import naming

CHUNKER_SCHEMA = {
    "properties": {
        "chunk_size": {"type": "integer", "default": 1000},
        "overlap": {"type": "integer", "default": 200},
    }
}


def test_a_parameter_left_out_takes_the_schema_default() -> None:
    params = {"chunk_size": 500}

    assert naming.schema_value(params, CHUNKER_SCHEMA, "chunk_size") == 500
    assert naming.schema_value(params, CHUNKER_SCHEMA, "overlap") == 200
    assert naming.schema_value(params, CHUNKER_SCHEMA, "unknown") is None


def test_profile_names_show_the_component_and_the_parameters_that_matter() -> None:
    assert naming.component_label("pypdf", "1") == "pypdf@1"
    assert (
        naming.chunking_profile_name("recursive@1", chunk_size=500, overlap=50)
        == "recursive@1 500/50"
    )
    assert (
        naming.embedding_profile_name(
            "openai@1", model="text-embedding-3-small", dimensions=1536
        )
        == "openai@1 text-embedding-3-small 1536d"
    )
    assert naming.vector_store_profile_name("qdrant@1", space="cosine") == (
        "qdrant@1 cosine"
    )
    assert (
        naming.retrieval_profile_name("dense", top_k=10, score_threshold=None)
        == "dense top-10"
    )
    assert (
        naming.retrieval_profile_name("dense", top_k=10, score_threshold=0.3)
        == "dense top-10 ≥0.3"
    )


def test_composed_names_read_from_the_documents_to_the_search() -> None:
    configuration = naming.chunking_configuration_name("pypdf@1", "recursive@1 500/50")

    assert configuration == "pypdf@1 → recursive@1 500/50"
    assert (
        naming.index_build_name(
            "contracts", "v1", configuration, "openai@1 m", "qdrant@1 cosine"
        )
        == "contracts v1 · pypdf@1 → recursive@1 500/50 · openai@1 m · qdrant@1 cosine"
    )
    assert (
        naming.variant_name(
            configuration, "openai@1 m", "qdrant@1 cosine", "dense top-5"
        )
        == "pypdf@1 → recursive@1 500/50 · openai@1 m · qdrant@1 cosine · dense top-5"
    )


def test_a_hash_suffix_is_added_only_when_the_name_is_taken() -> None:
    assert naming.disambiguated("pypdf@1", "abcdef123456", taken=False) == "pypdf@1"
    assert naming.disambiguated("pypdf@1", "abcdef123456", taken=True) == (
        "pypdf@1 #abcdef"
    )
