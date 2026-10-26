# qa_sets

Question sets with the documents that contain their answer, the answer expected and the
chunks a person confirmed as evidence, and the immutable snapshots an experiment is run on.
This is the "gold" retrieval is measured against: for each question, which files hold the
answer (document level) and, per chunking configuration, which chunks (chunk level).

The gold at chunk level is never imported: which chunks hold the answer depends on a chunking
configuration, so a person confirms it, configuration by configuration. There is no stored
text quote of the evidence: the evidence is the set of confirmed chunks.

## Entities (`models.py`)

| Entity | Identity |
|---|---|
| `QASet` | A named set of questions. Its origin corpus is only where the questions were written and where gold file names are resolved: it is not a constraint, so a set stays usable on any corpus snapshot that holds its gold documents. The constraint is checked when an experiment is created |
| `Question` | Text, tags, `answerable`. Editable until a snapshot holds it, then immutable and shared by every experiment that evaluates it. `replaced_by_question_id` points to the question that replaced it (see Authoring) |
| `GoldDocument` | `(question, document)`: a **list**, because a paragraph repeated in three attachments has three valid gold documents |
| `ExpectedAnswer` | An acceptable answer to a question, with an optional rubric for the judge; several per question, `is_primary` marks the reference one |
| `EvidenceLink` | `(question, chunking configuration)`: the review of which chunks hold the answer, with `status` `to_review` (a draft), `confirmed` or `not_found`, and who decided and when. No row means *not reviewed*, which is different from `not_found` (*reviewed: the evidence is not in these chunks*) |
| `EvidenceLinkChunk` | A chunk of a link, `sufficient` (answers alone) or `supporting`, with an optional graded relevance 0-3. Chunks are referenced with `RESTRICT`: a confirmed chunk cannot disappear |
| `QASetSnapshot` | An immutable freeze of the questions of a set, with `composition_hash` over the sorted question ids; unique per `(qa_set_id, composition_hash)` |
| `QASnapshotQuestion` | The composition of a snapshot; questions are referenced, never copied |

## Import (`utils.py`, `QASetService.import_file`)

`POST /qa-sets/{id}/import` takes a CSV or JSONL file.

| Field | Notes |
|---|---|
| `question` | Required |
| `answer` | Optional: the expected answer, stored as the primary `ExpectedAnswer` |
| `gold_files` | One or more files, separated by `\|` in a CSV, a list in JSONL. Each is a file name or a sha-256 (`sha256:` prefix optional). Required unless the question is not answerable |
| `tags` | Optional, separated by `\|` in a CSV |
| `answerable` | Optional, `true` when empty |

Files are resolved among the documents of the set's origin corpus (every document when the
set has none). The summary lists **every row**, none is dropped silently:

- `imported`: new questions, with the gold documents they resolved to;
- `existing`: the question text was already among the current questions of the set, so the row is left alone (its
  answer included) and a re-import adds nothing;
- `unresolved`: a gold file matches no document; `ambiguous`: it matches several (two
  documents with the same name), with the candidates and their content hashes so the row can
  be fixed by naming one by hash. A row with an unresolved or ambiguous file is **not**
  imported: guessing would put the wrong document in the gold;
- `invalid`: an empty question, an answerable one without gold files, an unreadable line.

## Authoring (`QuestionService`)

Questions are also written one by one (`POST /qa-sets/{id}/questions`), with tags, the
`answerable` flag, expected answers (one is primary; the first if none is marked) and,
optionally, gold documents. The text is unique among the current questions of a set,
because it is what an import deduplicates on (`409 question_already_in_set`).

- A question **no snapshot holds** is edited (`PATCH`) and deleted (`DELETE`) freely; its
  evidence links are kept on edit.
- A **frozen** question is neither edited nor deleted (`409 question_frozen`): snapshots
  reference questions, so editing one would change what past experiments measured. It is
  **replaced** (`POST /questions/{id}/replace`): a new question takes its place in the set,
  the old one gets `replaced_by_question_id` and leaves the listing, the next freeze and
  re-imports, while the snapshots that hold it are untouched. Evidence links are not copied
  to the new question. Deleting the new question clears the pointer and brings the old one
  back.
- **Gold documents** are set with their own call (`PUT /questions/{id}/gold-documents`),
  allowed on frozen questions too: they are an annotation of the question, and confirming
  evidence adds to them anyway. A document holding confirmed evidence chunks cannot be
  removed (`409 gold_document_has_evidence`). Gold documents must be in the origin corpus
  when the set has one.

## Evidence (`evidence.py`, `EvidenceService`)

`PUT /questions/{id}/evidence` writes the whole evidence of a question under one chunking
configuration, replacing what was there, so saving the same decision twice changes nothing:

| `status` | Chunks | `annotator` |
|---|---|---|
| `to_review` | any (a draft) | optional |
| `confirmed` | at least one | required |
| `not_found` | none | required |

Every chunk must be a chunk of that configuration (`422
evidence_chunks_outside_configuration`) and come from a document of the origin corpus; a
question that is not answerable has no evidence (`422 invalid_evidence`, with `reason`).
Confirming adds the documents of the chunks to the gold documents of the question and
returns them in `added_gold_document_ids`: annotating chunks yields the document-level gold
too. The annotator is a free name: there is no login, it records who decided, it does not
authorise.

`GET /qa-sets/{id}/evidence-coverage?chunking_configuration_id=` counts the answerable
current questions by status (`confirmed`, `not_found`, `to_review`, `not_reviewed`) and
gives the `recall_ceiling` of the configuration, `1 - not_found / (confirmed + not_found)`:
a question whose evidence is not among the chunks of a configuration cannot be retrieved
from them, whatever the embedder. The set detail reports each question's `evidence_status` under the configuration passed as
`chunking_configuration_id`.

## Export (`utils.py`, `QASetService.export`)

`GET /qa-sets/{id}/export?format=csv|jsonl[&snapshot_id=]` writes the current questions, or
those of a snapshot, in the format the import reads: importing the file back recreates the
questions, their primary answer, tags and gold documents. A gold file is written by name,
or as `sha256:…` when another document in the corpus has the same name, so the re-import
never meets an ambiguous name. Evidence links are not exported: they are ids of this
installation's chunks.

## Freeze (`QASetSnapshotService`)

`POST /qa-sets/{id}/snapshots` freezes the current questions through
`core/get_or_create.py`: freezing the same questions twice returns the same snapshot and says
so (`created: false`), because two snapshots of one composition would split the results of
experiments that are really comparable.

## Routes

| Route | Purpose |
|---|---|
| `POST /qa-sets`, `GET /qa-sets` | Create a set; list with question counts |
| `GET /qa-sets/{id}?limit=&offset=&chunking_configuration_id=` | A set with a page of its current questions, their gold documents, expected answers, `frozen` flag and, with a configuration, `evidence_status` |
| `POST /qa-sets/{id}/questions` | Write a question |
| `GET /qa-sets/{id}/evidence-coverage?chunking_configuration_id=` | Questions counted by evidence status, and the recall ceiling |
| `GET /qa-sets/{id}/export?format=&snapshot_id=` | CSV or JSONL download, readable by the import |
| `GET /questions/{id}[?chunking_configuration_id=]`, `PATCH /questions/{id}`, `DELETE /questions/{id}` | Read; edit or delete a question no snapshot holds |
| `POST /questions/{id}/replace` | Replace a question, frozen or not, with a new one |
| `PUT /questions/{id}/gold-documents` | Set the gold documents |
| `GET /questions/{id}/evidence?chunking_configuration_id=`, `PUT /questions/{id}/evidence` | Read; save a draft, confirm, or record not found |
| `POST /qa-sets/{id}/import` | Multipart `file` (CSV or JSONL); returns the summary above |
| `POST /qa-sets/{id}/snapshots`, `GET /qa-sets/{id}/snapshots` | Freeze (idempotent); list |

## Dependencies

Depends on `corpora` (origin corpus, membership), `documents` (resolution of gold files),
`pipelines` (chunking configurations) and `artifacts` (the chunks evidence points to).
`experiments` depends on this module, never the reverse.
