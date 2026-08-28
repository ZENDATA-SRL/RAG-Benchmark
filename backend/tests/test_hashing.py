from __future__ import annotations

import uuid

from src.core.hashing import (
    cache_key,
    chain_fingerprint,
    combined_config_hash,
    composition_hash,
    config_hash,
    hash_json,
    hash_parts,
)


def test_hash_parts_separates_parts_with_nul() -> None:
    """("ab", "c") and ("a", "bc") must not collide, or two configs could share a cache."""
    assert hash_parts("ab", "c") != hash_parts("a", "bc")


def test_hash_parts_is_deterministic() -> None:
    assert hash_parts("a", "b") == hash_parts("a", "b")


def test_hash_parts_is_order_sensitive() -> None:
    assert hash_parts("a", "b") != hash_parts("b", "a")


def test_composition_hash_ignores_order() -> None:
    """A snapshot is a set of documents: the selection order must not change its identity."""
    first, second, third = (uuid.uuid4() for _ in range(3))
    assert composition_hash([first, second, third]) == composition_hash([third, first, second])


def test_composition_hash_ignores_duplicates() -> None:
    """Selecting the same document twice is the same corpus composition."""
    document_id = uuid.uuid4()
    other_id = uuid.uuid4()
    assert composition_hash([document_id, other_id, document_id]) == composition_hash(
        [document_id, other_id]
    )


def test_composition_hash_distinguishes_different_sets() -> None:
    assert composition_hash([uuid.uuid4()]) != composition_hash([uuid.uuid4()])


def test_hash_json_ignores_key_order() -> None:
    """Two identical configurations written in a different key order share one row."""
    assert hash_json({"a": 1, "b": 2}) == hash_json({"b": 2, "a": 1})


def test_hash_json_ignores_whitespace_in_nested_structures() -> None:
    assert hash_json({"outer": {"y": [1, 2], "x": None}}) == hash_json(
        {"outer": {"x": None, "y": [1, 2]}}
    )


def test_hash_json_is_order_sensitive_for_lists() -> None:
    """Lists are ordered data, e.g. the chunker separators: order is meaningful."""
    assert hash_json([1, 2]) != hash_json([2, 1])


def test_hash_json_distinguishes_types() -> None:
    assert hash_json({"a": 1}) != hash_json({"a": "1"})


def test_config_hash_depends_on_component_version() -> None:
    """The same params on a different implementation are a different configuration."""
    params = {"chunk_size": 1000}
    assert config_hash(uuid.uuid4(), params) != config_hash(uuid.uuid4(), params)


def test_config_hash_depends_on_params() -> None:
    version_id = uuid.uuid4()
    assert config_hash(version_id, {"chunk_size": 1000}) != config_hash(
        version_id, {"chunk_size": 500}
    )


def test_config_hash_ignores_param_key_order() -> None:
    version_id = uuid.uuid4()
    assert config_hash(version_id, {"a": 1, "b": 2}) == config_hash(version_id, {"b": 2, "a": 1})


def test_combined_config_hash_is_order_sensitive() -> None:
    """The parsing and chunking hashes are combined in a fixed order, never swapped."""
    left, right = hash_json({"a": 1}), hash_json({"b": 2})
    assert combined_config_hash(left, right) != combined_config_hash(right, left)


def test_cache_key_depends_on_content_and_config() -> None:
    content = hash_json("content")
    config = hash_json({"chunk_size": 1000})
    assert cache_key(content, config) != cache_key(content, hash_json({"chunk_size": 500}))
    assert cache_key(content, config) != cache_key(hash_json("other"), config)


def test_cache_key_is_stable_for_the_same_inputs() -> None:
    """Re-acquiring the same file with the same profile must hit the existing artefact."""
    content = hash_json("content")
    config = hash_json({"chunk_size": 1000})
    assert cache_key(content, config) == cache_key(content, config)


def test_chain_fingerprint_covers_every_stage() -> None:
    """Changing any stage of the chain must produce a different index build identity."""
    parts = [hash_json(index) for index in range(4)]
    baseline = chain_fingerprint(*parts)
    for index in range(4):
        changed = list(parts)
        changed[index] = hash_json("changed")
        assert chain_fingerprint(*changed) != baseline
