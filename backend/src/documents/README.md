# documents

The uploaded files and their acquisition history.

- **`Document`** (`models.py`): one row per distinct content, unique on `content_hash`. Holds
  filename, MIME type, size, storage URI, user metadata and `document_status`.
- **Provenance** lives in `sources/` (`document_provenances`): every acquisition of a file
  is recorded, so uploading the same file twice gives one document and two provenances.

## Upload flow

`upload.py::run_upload` is the entry point shared by `POST /documents/upload` and
`POST /corpora/{id}/documents/upload`:

1. Opens an import run (`sources.UploadImportService`).
2. For each file, `DocumentService.ingest_upload` spools the stream to a temporary file while
   computing the hash, enforcing `max_upload_bytes` and the MIME allow-list
   (`allowed_mime_types`, PDF only for now), and rejecting empty files.
3. Looks the document up by `content_hash` or creates it; stores the bytes at
   `documents/{content_hash}/{filename}` only when new.
4. Records provenance and a per-file outcome (`imported`, `skipped_duplicate`,
   `skipped_unsupported`, `failed`). One bad file does not fail the batch.
5. With a `corpus_id`, adds the resulting documents to that corpus.

## Routes

`POST /documents/upload`, `GET /documents`, `GET /documents/{id}` (with provenances),
`PATCH /documents/{id}/metadata`, `GET /documents/{id}/content` (streams the original).
