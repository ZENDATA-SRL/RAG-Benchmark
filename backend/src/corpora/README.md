# corpora

Mutable sets of documents, and the immutable snapshots taken from them.

- **`Corpus`** and **`CorpusDocument`** (membership). Adding or removing documents is free
  and does not affect anything already built.
- **`CorpusSnapshot`** and **`CorpusSnapshotDocument`**: a frozen selection of a corpus's
  documents. `CorpusSnapshotService.get_or_create_reporting` deduplicates on
  `(corpus_id, composition_hash)`, where the hash covers the *set* of document ids, so two
  snapshots of the same documents are the same row. This keeps experiments on the same
  search space comparable. An empty selection or a document outside the corpus is rejected.
  Without explicit ids, every `stored` document of the corpus is frozen: pending or failed
  acquisitions cannot be parsed and would only fail the index build.
- A corpus with snapshots cannot be deleted (`CorpusHasSnapshotsError`).

An `IndexBuild` (in `indexes/`) references a snapshot, which is how the search space is
fixed. The worker reads snapshot documents through `CorpusSnapshotRepository`, a page of
ids at a time (`list_snapshot_document_ids`), so a large snapshot never travels in a
workflow payload.

## Routes

`POST/GET /corpora`, `GET/PATCH/DELETE /corpora/{id}`, `GET/POST /corpora/{id}/documents`,
`DELETE /corpora/{id}/documents/{document_id}`, `POST /corpora/{id}/documents/upload`,
`GET /corpora/{id}/progress` (documents per acquisition status).

| Snapshot route | Purpose |
|---|---|
| `POST /corpora/{id}/snapshots` | `{label, document_ids?}`. Answers `created`; a reused snapshot keeps its original label and `detail` says so (`constants.py`) |
| `GET /corpora/{id}/snapshots` | Paginated, newest first |
| `GET /corpora/{id}/snapshots/{snapshot_id}` | One snapshot; 404 if it belongs to another corpus |
| `GET /corpora/{id}/snapshots/{snapshot_id}/documents` | The frozen documents |
