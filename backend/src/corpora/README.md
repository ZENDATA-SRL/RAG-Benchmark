# corpora

Mutable sets of documents, and the immutable snapshots taken from them.

- **`Corpus`** and **`CorpusDocument`** (membership). Adding or removing documents is free
  and does not affect anything already built.
- **`CorpusSnapshot`** and **`CorpusSnapshotDocument`**: a frozen selection of a corpus's
  documents. `CorpusSnapshotService.get_or_create` deduplicates on
  `(corpus_id, composition_hash)`, where the hash covers the *set* of document ids, so two
  snapshots of the same documents are the same row. This keeps experiments on the same
  search space comparable. An empty selection or a document outside the corpus is rejected.
- A corpus with snapshots cannot be deleted (`CorpusHasSnapshotsError`).

An `IndexBuild` (in `pipelines/`) references a snapshot, which is how the search space is
fixed. The pipelines worker activities read snapshot documents through
`CorpusSnapshotRepository`.

## Routes

`POST/GET /corpora`, `GET/PATCH/DELETE /corpora/{id}`, `GET/POST /corpora/{id}/documents`,
`DELETE /corpora/{id}/documents/{document_id}`, `POST /corpora/{id}/documents/upload`,
`GET /corpora/{id}/progress` (documents per acquisition status). There is no snapshot route yet:
snapshots are created through the service.
