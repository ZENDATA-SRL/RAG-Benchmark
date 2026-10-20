# sources

Where documents come from, and the audit trail of every acquisition.

| Model | Meaning |
|---|---|
| `SourceConnection` | A reusable connection to a document system. Stores only a *reference* to credentials, never the secret (RT-S01) |
| `ImportSelection` | What to import from a connection |
| `ImportRun` / `ImportFileResult` | One batch, and the outcome of each file in it |
| `DocumentProvenance` | Links a document to the run and connection it was acquired from; mandatory for every document (RF-S05) |

Only the built-in **manual upload** source exists today. `seed.py::seed_upload_source` creates
its singleton connection and selection at startup, so provenance can always be recorded.
`UploadImportService` opens and closes runs and records file results; it is called by
`documents/upload.py`. The enums already list `filesystem`, `s3`, `sharepoint`,
`confluence`, but no connector is implemented and there are no routes in this module.
