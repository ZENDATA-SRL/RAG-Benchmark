# transfers

Makes chunk-level gold cheap. A **job** ranks, for each question of a QA set, every chunk
of its gold documents in a target chunking configuration, so the review starts from the
likely chunks instead of a search through the document. One mechanism, two uses:

- **Proposal** (no source configuration): imported questions come with gold documents but
  no chunks; the question and its primary expected answer are what the chunks are compared
  with.
- **Transfer** (with a source configuration): the chunks confirmed in another parser or
  chunker are looked for among the chunks of the target.

A job only proposes. The decision is the question's evidence, written by a person through
`PUT /questions/{id}/evidence` like any other annotation: nothing becomes gold without a
confirmation.

## Entities (`models.py`)

| Entity | Role |
|---|---|
| `TransferJob` | QA set, source (nullable) and target configuration, the embedder of the semantic signal (nullable), `signal_weights` and `confidence_thresholds` as used, `status` (`pending`, `running`, `completed`, `failed`, `cancelled`), a `progress` copy for polling, `recall_ceiling` |
| `TransferQuestion` | A question the job ranks, with its status and candidate count: the unit of idempotency and resume |
| `TransferCandidate` | A chunk of the target proposed for a question: combined, semantic, lexical and positional scores, confidence band, `preselected`, `suggested_relevance` (with a source, the grade of the confirmed chunk it matches) and rank |

## Creating a job (`TransferService.create`)

The job takes the answerable current questions of the set, or of `question_ids`, that are
**not decided** in the target: a question confirmed or marked not found there is a human
decision, and a job never puts it back into question (`skipped.already_decided`). With a
source, only the questions confirmed in the source are taken (`skipped.not_confirmed_in_source`).

The candidates of a question are the chunks of its gold documents in the target, so a
question whose gold documents are not all materialised there (or that has none) cannot be
ranked: `422 uncovered_questions_choice_required` lists them, and `exclude_uncovered: true`
leaves them out (`excluded` in the response). `422 nothing_to_transfer` when nothing is
left, `422 same_configuration` when the source is the target.

The embedder is `embedding_profile_id`, or the one of the newest ready index built on the
target; with neither, the semantic signal is skipped and the ranking rests on the words.

## Ranking (`ranking.py`, `matching.py`)

The worker's `TransferDatasetWorkflow` ranks the questions one by one through
`TransferRanker.rank`. For a question:

- **Reference**: with a source, the text of its confirmed chunks there; without, the
  question followed by its primary expected answer.
- **Pool**: every chunk of its gold documents in the target, in full: no top-k, the right
  chunk must be in the list even when the signals put it low.
- **Signals** (`matching.py`, pure and tested without a database):
  - *semantic*: the best cosine between the candidate and any reference, with the job's
    embedder;
  - *lexical*: with a source, how much of one passage is the other by word trigrams, both
    ways (a target chunk may hold the whole source chunk or be a piece of it), after a
    normalisation of what parsers disagree on (unicode forms and ligatures, quotes, dashes,
    soft hyphens, words split across lines, table separators, whitespace, case); without a
    source, the share of the reference's words the candidate contains;
  - *positional*: with a source, closeness to the nearest confirmed chunk of the same
    document, by page when both pages are known, else by relative place (of the middle
    of the chunk, so that chunkers of different sizes agree); none without one.
- **Combined**: the weighted mean of the signals that apply (a missing one is left out and
  the others reweighted, not counted as 0). Bands: `high` from 0.75, `low` below 0.45.
- **Pre-selection**: only a near-identical copy of a source chunk (lexical ≥ 0.9), which is
  then `high` and first whatever the other signals say. **Never without a source**: a
  question and its answer are not an extract of the document.

Weights and thresholds above are starting values, saved on each job and settable when it
is created; calibrating them on a real corpus is done by launching jobs, not in code.

A failure of the embedder is raised so the workflow retries it with backoff; any other
error fails only that question. A question already ranked is never ranked again, so a
resumed job continues where it stopped.

Unlike creation, a resume does not skip the questions decided in the target since the job
was created: they are ranked anyway, then shown as `decided`. This happens, for instance,
with a second job created while the first one was still under review, cancelled, and
resumed once that review is over. Nothing is lost or overwritten, since a job never writes
the evidence, but the ranking (and its embedder calls) is wasted.

## Review

The queue lists the job's questions with a state: `preselected`, `to_review` (candidates in
the high or medium band), `no_candidates`, `pending` (not ranked yet), `failed`, `decided`
(confirmed or not found in the target). Without a filter the questions waiting for a
person come first, the near-certain ones on top. Progress (`reviewed`, `confirmed`,
`not_found`) and the recall ceiling of the target on the whole set are read live from the
evidence, so a decision shows at once.

## Routes

| Route | Purpose |
|---|---|
| `POST /transfers` | Create a job and start its workflow (`202`) |
| `GET /transfers[?qa_set_id=]`, `GET /transfers/{id}` | Jobs with progress and recall ceiling |
| `POST /transfers/{id}/cancel`, `POST /transfers/{id}/resume` | Stop ranking (`409` once ended); relaunch ranking only the questions left (`409` if running or all ranked) |
| `GET /transfers/{id}/questions[?state=]` | The review queue |
| `GET /transfers/{id}/questions/{question_id}` | A question opened for review: its candidates best first with the three scores, the source chunks it is matched to, and the next question waiting |

Full-text search for evidence no candidate caught is `GET /chunks/search` in `artifacts`.

## Dependencies

Depends on `qa_sets` (questions, gold documents, evidence), `pipelines` (configurations,
embedding profiles), `artifacts` (chunks) and `retrieval` (the embedders shared with the
worker). The worker's `temporal/activities/transfer.py` calls `ranking.py`.
