from __future__ import annotations

# Message attached whenever a get-or-create returned a pre-existing row. Deduplication is by
# the hash of the behaviour and the name is excluded from it, so without saying this
# the user is left wondering where the name they typed went. Shared by every module whose
# rows are deduplicated by configuration (profiles, chunking configurations, index builds).
REUSED_DETAIL = (
    "an identical configuration already existed and was reused; the name you supplied was "
    "not applied, because profiles are deduplicated by their parameters and not by name"
)
