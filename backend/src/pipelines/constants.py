from __future__ import annotations

from src.infrastructure.database.enums import RetrievalStrategy

# Message attached whenever a get-or-create returned a pre-existing row. Deduplication is by
# the hash of the behaviour and the name is excluded from it, so without saying this
# the user is left wondering where the name they typed went. Shared by every module whose
# rows are deduplicated by configuration (profiles, chunking configurations, index builds).
REUSED_DETAIL = (
    "an identical configuration already existed and was reused, since profiles are "
    "deduplicated by their parameters"
)

# Retrieval strategies the engine executes today. The enum lists the others so profiles can
# name them once they exist, but creating one now is refused.
SUPPORTED_RETRIEVAL_STRATEGIES = (RetrievalStrategy.DENSE,)
