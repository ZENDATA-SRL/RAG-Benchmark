"""Names derived from what an entity is, never typed by the user.

A name has to say what is being worked on: a free label ("test 2", "good one") says
nothing a week later, and since profiles are deduplicated by content the label of the
first creator would stick to every later identical request anyway. Each name shows the
component with its version and the parameters that tell two siblings apart; a short
suffix of the content hash is added only when two different rows would still read the
same.
"""

from __future__ import annotations

from typing import Any

HASH_SUFFIX_LENGTH = 6


def component_label(key: str, version: str) -> str:
    """`pypdf@1`: a component and the version whose behaviour the profile pins."""
    return f"{key}@{version}"


def schema_value(params: dict[str, Any], schema: dict[str, Any], key: str) -> Any:
    """The value a component receives for a parameter: the given one or its default."""
    if key in params:
        return params[key]
    return (schema.get("properties") or {}).get(key, {}).get("default")


def parsing_profile_name(component: str) -> str:
    return component


def chunking_profile_name(
    component: str, *, chunk_size: int | None, overlap: int | None
) -> str:
    """`recursive@1 1000/200`: chunk size over overlap, the knobs every chunker has."""
    if chunk_size is None:
        return component
    if overlap is None:
        return f"{component} {chunk_size}"
    return f"{component} {chunk_size}/{overlap}"


def embedding_profile_name(
    component: str, *, model: str | None, dimensions: int | None
) -> str:
    """`openai@1 text-embedding-3-small 1536d`: the model is what changes the vectors."""
    parts = [component]
    if model:
        parts.append(str(model))
    if dimensions:
        parts.append(f"{dimensions}d")
    return " ".join(parts)


def vector_store_profile_name(component: str, *, space: str | None) -> str:
    """`qdrant@1 cosine`: the distance is what changes the ranking."""
    return f"{component} {space}" if space else component


def retrieval_profile_name(
    strategy: str, *, top_k: int, score_threshold: float | None
) -> str:
    """`dense top-10`, with `≥0.3` when a score threshold cuts the hits."""
    name = f"{strategy} top-{top_k}"
    if score_threshold is not None:
        name += f" ≥{score_threshold:g}"
    return name


def chunking_configuration_name(parsing: str, chunking: str) -> str:
    """`pypdf@1 → recursive@1 1000/200`: the parse feeds the chunker."""
    return f"{parsing} → {chunking}"


def index_build_name(
    corpus: str, snapshot: str, configuration: str, embedding: str, vector_store: str
) -> str:
    """The documents (corpus and snapshot), then everything their vectors depend on.

    The corpus is named because snapshot labels restart in each corpus.
    """
    return f"{corpus} {snapshot} · {configuration} · {embedding} · {vector_store}"


def variant_name(
    configuration: str, embedding: str, vector_store: str, retrieval_profile: str
) -> str:
    """What a variant searches and how, without the snapshot all variants share."""
    return f"{configuration} · {embedding} · {vector_store} · {retrieval_profile}"


def disambiguated(name: str, digest: str, *, taken: bool) -> str:
    """Append a short content hash when another row already reads the same."""
    return f"{name} #{digest[:HASH_SUFFIX_LENGTH]}" if taken else name
