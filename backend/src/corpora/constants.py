from __future__ import annotations

# Message attached when a snapshot request matched an existing composition. Snapshots are
# deduplicated by their documents and not by label, so the label in the request is not the
# one the caller gets back.
SNAPSHOT_REUSED_DETAIL = (
    "a snapshot with the same documents already existed and was reused; the label you "
    "supplied was not applied, because snapshots are deduplicated by their composition"
)
