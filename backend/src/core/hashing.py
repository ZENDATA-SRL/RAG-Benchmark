from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterable
from typing import Any


def hash_parts(*parts: str) -> str:
    """Hash an ordered sequence of strings into a hex sha-256 digest.

    Parts are separated by a NUL byte so that ("ab", "c") and ("a", "bc") differ.

    Args:
        *parts: Ordered components of the identity being hashed.

    Returns:
        Hex-encoded sha-256 digest.
    """
    digest = hashlib.sha256()
    for index, part in enumerate(parts):
        if index:
            digest.update(b"\x00")
        digest.update(part.encode("utf-8"))
    return digest.hexdigest()


def composition_hash(document_ids: Iterable[uuid.UUID]) -> str:
    """Hash the composition of a corpus snapshot (RF-C07).

    Ids are deduplicated and sorted, so the hash depends on the *set* of documents
    and not on the order in which the user selected them.

    Args:
        document_ids: Documents frozen into the snapshot.

    Returns:
        Hex-encoded sha-256 digest over the sorted document ids.
    """
    return hash_parts(*sorted({str(document_id) for document_id in document_ids}))


def hash_json(value: Any) -> str:
    """Hash a JSON-compatible value canonically.

    Keys are sorted and separators normalised, so the same configuration written with a
    different key order or spacing yields the same hash. UUIDs must be converted to
    strings by the caller.

    Args:
        value: JSON-compatible value, typically a mapping of parameters.

    Returns:
        Hex-encoded sha-256 digest.
    """
    return hash_parts(_canonical_json(value))


def config_hash(component_version_id: uuid.UUID, params: Any) -> str:
    """Hash a pipeline profile: component version + behavioural parameters.

    Args:
        component_version_id: Implementation the profile is built on.
        params: Profile parameters, hashed canonically.

    Returns:
        Hex-encoded sha-256 digest.
    """
    return hash_parts(str(component_version_id), _canonical_json(params))


def combined_config_hash(*config_hashes: str) -> str:
    """Hash a configuration composed of other configurations.

    Used by `chunking_configurations`, whose hash is built from the parsing and chunking
    profile hashes, so the pair is identified by what its components do and not by the
    surrogate ids they happen to have.

    Args:
        *config_hashes: Component hashes, in a fixed order.

    Returns:
        Hex-encoded sha-256 digest.
    """
    return hash_parts(*config_hashes)


def cache_key(content_hash: str, config_hash_value: str) -> str:
    """Hash the cache key of a per-document artefact (RF-P07).

    Used by `parsing_results` (document content hash + parsing profile hash) and by
    `chunk_results` (document content hash + chunking configuration hash). It depends on
    the *content* of the document, so the same file acquired twice reuses the artefact.

    Args:
        content_hash: `documents.content_hash` of the input document.
        config_hash_value: `config_hash` of the profile or configuration.

    Returns:
        Hex-encoded sha-256 digest.
    """
    return hash_parts(content_hash, config_hash_value)


def chain_fingerprint(
    snapshot_composition_hash: str,
    chunking_configuration_hash: str,
    embedding_config_hash: str,
    vector_store_config_hash: str,
) -> str:
    """Hash the whole vector DB population chain of an index build (RF-P09).

    Covers everything the content of the index depends on — search space included —
    so repeating the same choice reuses the existing build instead of rebuilding it.

    Args:
        snapshot_composition_hash: `corpus_snapshots.composition_hash`.
        chunking_configuration_hash: `chunking_configurations.config_hash`.
        embedding_config_hash: `embedding_profiles.config_hash`.
        vector_store_config_hash: `vector_store_profiles.config_hash`.

    Returns:
        Hex-encoded sha-256 digest.
    """
    return hash_parts(
        snapshot_composition_hash,
        chunking_configuration_hash,
        embedding_config_hash,
        vector_store_config_hash,
    )


def _canonical_json(value: Any) -> str:
    """Serialise a JSON-compatible value deterministically."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
