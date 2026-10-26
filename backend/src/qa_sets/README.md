# qa_sets

Question sets with the documents that contain their answer and the answer expected, and the
immutable snapshots an experiment is run on. This is the "gold" a retrieval experiment is
measured against at document level: for each question, which files hold the answer.

The gold at chunk level is not imported: which chunks hold the answer depends on a chunking
configuration, so it is proposed within the gold documents and confirmed by a person. There
is no stored text quote of the evidence: the evidence is the set of confirmed chunks.

## Entities (`models.py`)

| Entity | Identity |
|---|---|
| `QASet` | A named set of questions. Its origin corpus is only where the questions were written and where gold file names are resolved: it is not a constraint, so a set stays usable on any corpus snapshot that holds its gold documents. The constraint is checked when an experiment is created |
| `Question` | Text, tags, `answerable`. Immutable and shared by every experiment that evaluates it |
| `GoldDocument` | `(question, document)`: a **list**, because a paragraph repeated in three attachments has three valid gold documents |
| `ExpectedAnswer` | An acceptable answer to a question, with an optional rubric for the judge; several per question, `is_primary` marks the reference one |
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
- `existing`: the question text was already in the set, so the row is left alone (its
  answer included) and a re-import adds nothing;
- `unresolved`: a gold file matches no document; `ambiguous`: it matches several (two
  documents with the same name), with the candidates and their content hashes so the row can
  be fixed by naming one by hash. A row with an unresolved or ambiguous file is **not**
  imported: guessing would put the wrong document in the gold;
- `invalid`: an empty question, an answerable one without gold files, an unreadable line.

## Freeze (`QASetSnapshotService`)

`POST /qa-sets/{id}/snapshots` freezes the current questions through
`core/get_or_create.py`: freezing the same questions twice returns the same snapshot and says
so (`created: false`), because two snapshots of one composition would split the results of
experiments that are really comparable.

## Routes

| Route | Purpose |
|---|---|
| `POST /qa-sets`, `GET /qa-sets` | Create a set; list with question counts |
| `GET /qa-sets/{id}?limit=&offset=` | A set with a page of its questions, their gold documents and expected answers |
| `POST /qa-sets/{id}/import` | Multipart `file` (CSV or JSONL); returns the summary above |
| `POST /qa-sets/{id}/snapshots`, `GET /qa-sets/{id}/snapshots` | Freeze (idempotent); list |

## Dependencies

Depends on `corpora` (origin corpus, membership) and `documents` (resolution of gold files).
`experiments` depends on this module, never the reverse.
