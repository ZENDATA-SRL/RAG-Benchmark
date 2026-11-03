from __future__ import annotations

import re
import uuid
from collections.abc import Sequence

# A document is `d<n>`, numbered from 1 in the job's order, and a chunk is `d<n>:c<ordinal>`.
# Short and derived from what the chunk is, so the model does not copy long ids, a chunk
# has the same reference in every unit of a job, and nothing has to be remembered.
_DOCUMENT = re.compile(r"^d(\d+)$")
_CHUNK = re.compile(r"^d(\d+):c(\d+)$")


def chunk_ref(document_ref: str, ordinal: int) -> str:
    return f"{document_ref}:c{ordinal}"


class Refs:
    """The short references of the documents of a job, and the chunks within them."""

    def __init__(self, document_ids: Sequence[uuid.UUID]) -> None:
        self.document_ids = list(document_ids)
        self._index = {
            document_id: i for i, document_id in enumerate(self.document_ids)
        }

    def document(self, document_id: uuid.UUID) -> str:
        return f"d{self._index[document_id] + 1}"

    def chunk(self, document_id: uuid.UUID, ordinal: int) -> str:
        return chunk_ref(self.document(document_id), ordinal)

    def resolve_document(self, ref: str) -> uuid.UUID | None:
        """The document a reference names, or `None` if it names none of the job's."""
        match = _DOCUMENT.match(ref.strip().lower())
        if match is None:
            return None
        index = int(match.group(1)) - 1
        if not 0 <= index < len(self.document_ids):
            return None
        return self.document_ids[index]

    def resolve_chunk(self, ref: str) -> tuple[uuid.UUID, int] | None:
        """The document and the ordinal a chunk reference names, if it is well formed."""
        match = _CHUNK.match(ref.strip().lower())
        if match is None:
            return None
        document_id = self.resolve_document(f"d{match.group(1)}")
        if document_id is None:
            return None
        return document_id, int(match.group(2))
