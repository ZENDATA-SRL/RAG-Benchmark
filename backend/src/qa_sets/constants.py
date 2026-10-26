from __future__ import annotations

# Message attached when a freeze matched an existing composition: snapshots are
# deduplicated by their questions and not by label.
QA_SNAPSHOT_REUSED_DETAIL = (
    "a snapshot with the same questions already existed and was reused; the label you "
    "supplied was not applied, because snapshots are deduplicated by their composition"
)
