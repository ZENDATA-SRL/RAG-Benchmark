from __future__ import annotations

import math
from typing import Any

# The distance spaces a vector store profile may declare, in the vocabulary of its schema.
SPACES = ("cosine", "l2", "ip")
DEFAULT_SPACE = "cosine"

# Qdrant names its distances differently; Chroma uses the profile vocabulary as is.
QDRANT_DISTANCES = {"cosine": "Cosine", "l2": "Euclid", "ip": "Dot"}
SPACES_BY_QDRANT_DISTANCE = {value: key for key, value in QDRANT_DISTANCES.items()}


def profile_space(index_params: dict[str, Any]) -> str:
    """Return the distance space a vector store profile asks for.

    Every writer goes through this, so a profile without an explicit `space` gets the
    same distance on every vector store instead of each engine's own default.

    Raises:
        ValueError: If the profile declares a space no vector store supports.
    """
    space = index_params.get("space") or DEFAULT_SPACE
    if space not in SPACES:
        raise ValueError(f"unsupported distance space: {space!r}")
    return space


def euclidean_similarity(distance: float) -> float:
    """Turn a Euclidean distance into a score in (0, 1] where higher means closer."""
    return 1.0 / (1.0 + max(distance, 0.0))


def chroma_similarity(space: str, distance: float) -> float:
    """Normalise a distance as Chroma reports it into a higher-is-better score.

    Chroma reports `1 - cosine` for cosine, `1 - dot` for inner product and the squared
    Euclidean distance for l2. The result matches `qdrant_similarity` for the same
    vectors, so a score means the same thing whichever store holds the index.
    """
    if space == "l2":
        return euclidean_similarity(math.sqrt(max(distance, 0.0)))
    return 1.0 - distance


def qdrant_similarity(space: str, score: float) -> float:
    """Normalise a Qdrant score into a higher-is-better score.

    Qdrant already reports cosine and dot product as similarities, but the Euclidean
    distance as a distance.
    """
    if space == "l2":
        return euclidean_similarity(score)
    return score
