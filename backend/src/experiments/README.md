# experiments

Retrieval experiments: a comparison of **variants** (index build x retrieval profile) on one
corpus snapshot and one frozen question set, executed on Temporal and measured at document
level and, where the evidence is confirmed, at chunk level. Only `type = retrieval` exists;
the Q&A type is modelled and refused.

## Entities (`models.py`)

| Entity | Role |
|---|---|
| `Experiment` | Corpus snapshot, QA snapshot, repetitions, `uncovered_policy`. The snapshot is repeated here although derivable from the variants: it is the guard that makes "every variant searches the same documents" checkable |
| `Variant` | Index build x retrieval profile; one is the baseline (the first, if none is marked). Named after what it searches and how: configuration · embedder · vector store · retrieval profile, without the snapshot all variants share |
| `Run` | One execution, with `config_snapshot` (experiment, snapshots, variants, index builds and profiles **copied by value**, and the evidence the chunk metrics were scored on), the denormalised `progress` the UI polls, and `error` |
| `Execution` | Question x variant x repetition, unique per run: the unit of idempotency and resume |
| `RetrievalCall`, `RetrievalHit` | One call of the retrieval tool and the chunks it returned, with rank, score, stage, `relevant_document` and `relevant_chunk` |
| `MetricDefinition`, `Evaluator`, `Evaluation` | The catalog of metrics (each with its level, `document` or `chunk`), one deterministic evaluator per level, and one score (or exclusion with its reason) per execution and metric |
| `MetricAggregate` | Per run, variant, metric and slice: mean, standard deviation, median, p95, `n_effective`, `n_excluded` and `excluded_reasons` |

`executions`, `retrieval_calls` and `retrieval_hits` grow as questions x variants x
repetitions x top-k. They are not partitioned yet: with the volumes of a first experiment it
is not needed, but it is a debt to pay (for instance hash partitioning on `run_id`) before
runs of thousands of questions are common.

## Guards on creation (`ExperimentService.create`)

1. **Search space.** Every variant's index build must be built on the experiment's corpus
   snapshot, otherwise one variant would search 50 documents and another 200. `422
   variants_outside_snapshot`, listing the variants.
2. **Gold coverage.** Answerable questions whose gold documents are not all in the snapshot
   are listed (`GET /experiments/coverage` does the same check beforehand). The caller must
   choose: `uncovered_policy: "exclude"` runs them but leaves them out of the metrics'
   denominator with reason `gold_document_not_in_snapshot`; or widen the snapshot and create
   a new experiment. Without a choice: `422 gold_coverage_choice_required`. Counting them as
   retriever failures, which is what doing nothing would do, is the behaviour to avoid.

## Runs (`RunLauncher`, `RunService`)

`POST /experiments/{id}/runs` requires every variant's index build to be `ready`, creates
the run with its `config_snapshot` and every `pending` execution, and starts
`RunExperimentWorkflow` (id `run-experiment-{run_id}`, queue `experiments`). `concurrency`
(default 5) is the number of queries in flight, because query embeddings are rate limited.

- `POST …/runs/{run_id}/cancel` cancels the workflow and marks the run `failed` with
  `error = "cancelled"`.
- `POST …/runs/{run_id}/resume` relaunches an interrupted or partly failed run under the
  same workflow id: executions that succeeded are skipped, the others are redone.
- A question that fails marks only its execution `failed` with the reason, and the run
  goes on; the run is `succeeded` when every execution was attempted, with the failures
  counted in `progress` and excluded from the metrics (`execution_failed`).

`ExecutionRunner` (in `evaluation.py`) is what the worker's activity calls for one
execution: it runs `RetrievalService.search` in-process with the execution id, which records
the call and its hits, then scores the execution. A failure of the embedder or the vector
store is raised so the workflow retries it with backoff; any other domain error fails the
execution.

## Metrics (`metrics.py`, `evaluation.py`)

Computed per execution on the `final` hits of the `retrieved` scope, from the stored hits.
The cutoff k counts **retrieved chunks**, best first: `@5` judges the first five chunks, which
is what a generator would be given. The cutoffs are fixed and not the profile's top-k, so
`recall@5` means the same in every variant.

**Document level.** A chunk is relevant when the document it comes from is one of the
question's gold documents; a chunk with no known document keeps its place and is not
relevant.

| Metric | Definition |
|---|---|
| `recall@k`, k in 1, 3, 5, 10 | distinct gold documents reached by the first k chunks / gold documents |
| `precision@k` | relevant chunks among the first k / chunks among them (a query that retrieves fewer than k is judged on those it retrieved; nothing retrieved is 0) |
| `hit_rate@k` | 1 if any of the first k chunks is relevant |
| `mrr` | 1 / rank of the first relevant chunk, 0 if none |
| `first_relevant_rank` | that rank; empty (no score) when none was retrieved |

**Chunk level.** A chunk is relevant when it is a confirmed evidence chunk of the question
under the chunking configuration the variant searches (`variant → index build → chunking
configuration`): evidence confirmed under another configuration says nothing about these
chunks, which is why chunk metrics only compare variants of the same configuration. A chunk
retrieved twice by one execution keeps its first rank and counts once.

| Metric | Definition |
|---|---|
| `chunk_recall@k` | evidence chunks (sufficient or supporting) among the first k / evidence chunks |
| `chunk_precision@k` | evidence chunks among the first k / chunks among them |
| `chunk_hit_rate@k` | 1 if any of the first k chunks is an evidence chunk |
| `chunk_sufficient_hit@k` | 1 if the first k chunks are enough to answer: a sufficient chunk, or every supporting chunk when none is sufficient |
| `chunk_ndcg@k` | nDCG with the graded relevance as gain, or 2 for sufficient and 1 for supporting when no grade was given; empty if every gain is 0 |
| `chunk_mrr`, `chunk_first_relevant_rank` | as at document level, on the first evidence chunk |

The flags `relevant_document` and `relevant_chunk` are written on each hit so the drill-down
shows why a hit counts; `relevant_chunk` is empty when the chunk level does not apply.

**Exclusions.** Executions that do not count get an evaluation per metric with
`excluded = true` and the reason, and no score. At document level, in this order:
`not_answerable`, `no_gold_documents`, `gold_document_not_in_snapshot`, `execution_failed`.
At chunk level: `not_answerable`, then `evidence_not_reviewed` (no link under the
configuration, or a draft) and `evidence_not_found` (looked for and not among its chunks),
then `gold_document_not_in_snapshot` and `execution_failed`. A question can therefore count
for its documents and be left out for its chunks; a missing evidence is never scored 0.

**Aggregation.** At the end of the run `metric_aggregates` are written per variant and
metric, over all questions (`slice_key = all`) and over each question tag
(`slice_key = tag`). The repetitions of a question are averaged first and the statistics are
taken across questions, so `n_effective` counts questions: a question counts when one of its
repetitions has a score, and is excluded when all of them are, under the first of their
reasons. `n_excluded` and `excluded_reasons` (excluded questions by reason) account for the
rest (for `first_relevant_rank`, whose empty values are not scores, `n_effective` counts only
the found ones). Confidence intervals and significance tests are not computed.

**Evidence and re-evaluation.** The evidence keeps changing after a QA set is frozen, so the
chunk metrics of a run are computed on the evidence **at the time of scoring**. Closing a run
writes `config_snapshot.chunk_gold`: the time, a fingerprint of the links read and their
chunks, the counts per chunking configuration and the links with their status.
`POST …/runs/{run_id}/evaluate` re-scores a finished run from its stored hits (no retrieval
call is repeated), rewrites the aggregates and the record; `409 run_in_progress` while the run
is pending or running. Scoring it twice on the same evidence gives the same numbers and the
same fingerprint.

An experiment does not wait for the evidence to be complete: on a configuration whose
evidence is half reviewed, for instance during a transfer, the chunk metrics count the
confirmed questions and every other one is excluded with `evidence_not_reviewed` or
`evidence_not_found`, so the results say on how much they rest. The wizard shows the
evidence of each configuration of the chosen variants for the same reason.

`seed.py` registers the metric definitions and the two deterministic evaluators
(`document_level_retrieval`, `chunk_level_retrieval`) at startup and again, idempotently,
before evaluating, so a worker never depends on the API having started.

## Results (`results.py`)

| Route | Purpose |
|---|---|
| `POST /experiments`, `GET /experiments`, `GET /experiments/{id}` | Create (with the guards above); list; detail with variants, runs and coverage. Both list and detail name the corpus and the QA set behind the two snapshots (`corpus_id`, `corpus_name`, `corpus_snapshot_label`, `qa_set_id`, `qa_set_name`, `qa_set_snapshot_label`) |
| `GET /experiments/coverage?corpus_snapshot_id=&qa_set_snapshot_id=` | The questions with gold documents outside a corpus snapshot |
| `POST /experiments/{id}/runs`, `GET …/runs/{run_id}` | Launch (`202`, `started=false` if already running); read a run with progress and configuration, served from the row |
| `POST …/runs/{run_id}/cancel`, `POST …/runs/{run_id}/resume` | See above |
| `POST …/runs/{run_id}/evaluate` | Re-score a finished run on the current evidence; returns the run with its `chunk_gold` |
| `GET …/runs/{run_id}/results[?tag=]` | `groups`, one per chunking configuration (parser, chunker, `evidence_coverage`, `recall_ceiling`), each with its variants and their metrics at both levels with `n_effective`, `n_excluded` and `excluded_reasons`; `cross_group_metrics` names the keys that compare across groups (document level only) and why; `chunk_gold` gives the date and fingerprint of the evidence; and the corpus and QA snapshots |
| `GET …/runs/{run_id}/results.csv` | The same as CSV, one row per variant and metric, with the chunking configuration and the level |
| `GET …/runs/{run_id}/questions[?limit=&offset=]` | The questions of the run with each variant's first-repetition outcome at both levels |
| `GET …/runs/{run_id}/questions/{question_id}` | Drill-down: every variant's executions and hits (rank, score, file, page, text, `relevant_document`, `relevant_chunk` and its grade), the evidence status under its configuration and the evidence chunks, retrieved or not; the gold documents |

`recall_ceiling` is `1 - not_found / (confirmed + not_found)` on the evidence the run was
scored on: the share of the reviewed questions whose evidence exists among the chunks of the
configuration. It is a property of the configuration on the QA set, not of a variant, and
bounds what any variant of the group can reach on those questions.

## Dependencies

Depends on `qa_sets`, `corpora`, `indexes`, `pipelines` and `retrieval`. `retrieval` depends
back on `experiments.repository` only to record the calls of an execution. The worker's
`temporal/activities/experiments.py` calls the services here.
