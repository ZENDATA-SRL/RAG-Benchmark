# experiments

Retrieval experiments: a comparison of **variants** (index build x retrieval profile) on one
corpus snapshot and one frozen question set, executed on Temporal and measured at document
level. Only `type = retrieval` exists; the Q&A type is modelled and refused.

## Entities (`models.py`)

| Entity | Role |
|---|---|
| `Experiment` | Corpus snapshot, QA snapshot, repetitions, `uncovered_policy`. The snapshot is repeated here although derivable from the variants: it is the guard that makes "every variant searches the same documents" checkable |
| `Variant` | Index build x retrieval profile; one is the baseline (the first, if none is marked) |
| `Run` | One execution, with `config_snapshot` (experiment, snapshots, variants, index builds and profiles **copied by value**), the denormalised `progress` the UI polls, and `error` |
| `Execution` | Question x variant x repetition, unique per run: the unit of idempotency and resume |
| `RetrievalCall`, `RetrievalHit` | One call of the retrieval tool and the chunks it returned, with rank, score, stage and `relevant_document` |
| `MetricDefinition`, `Evaluator`, `Evaluation` | The catalog of metrics, the deterministic evaluator that scores them, and one score (or exclusion with its reason) per execution and metric |
| `MetricAggregate` | Per run, variant, metric and slice: mean, standard deviation, median, p95, `n_effective`, `n_excluded` |

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
A document is relevant when it is one of the question's gold documents; a document retrieved
through several chunks counts once, at the rank of its first chunk, and ranks are over
**distinct documents**.

| Metric | Definition |
|---|---|
| `recall@k`, k in 1, 3, 5, 10 | gold documents among the first k documents / gold documents |
| `precision@k` | gold documents among the first k documents / documents among them (a query that retrieves fewer than k is judged on those it retrieved; nothing retrieved is 0) |
| `hit_rate@k` | 1 if any gold document is among the first k |
| `mrr` | 1 / rank of the first gold document, 0 if none |
| `first_relevant_rank` | that rank; empty (no score) when none was retrieved |

The cutoffs are fixed and not the profile's top-k, so `recall@5` means the same in every
variant. The flag `relevant_document` is written on each hit so the drill-down shows why a
hit counts.

Executions that do not count get an evaluation per metric with `excluded = true` and the
reason, and no score. In this order: `not_answerable` (the question is flagged as not
answerable), `no_gold_documents`, `gold_document_not_in_snapshot`, `execution_failed`.
At the end of the run `metric_aggregates` are written per variant and metric, over all
questions (`slice_key = all`) and over each question tag (`slice_key = tag`).
`n_effective` is how many scores entered the statistics and `n_excluded` how many
evaluations were left out, so together they account for every execution of the variant
(for `first_relevant_rank`, whose empty values are not scores, `n_effective` counts only the
found ones). Confidence intervals and significance tests are not computed.

`seed.py` registers the metric definitions and the deterministic evaluator at startup and
again, idempotently, before evaluating, so a worker never depends on the API having started.

## Results (`results.py`)

| Route | Purpose |
|---|---|
| `POST /experiments`, `GET /experiments`, `GET /experiments/{id}` | Create (with the guards above); list; detail with variants, runs and coverage |
| `GET /experiments/coverage?corpus_snapshot_id=&qa_set_snapshot_id=` | The questions with gold documents outside a corpus snapshot |
| `POST /experiments/{id}/runs`, `GET …/runs/{run_id}` | Launch (`202`, `started=false` if already running); read a run with progress and configuration, served from the row |
| `POST …/runs/{run_id}/cancel`, `POST …/runs/{run_id}/resume` | See above |
| `GET …/runs/{run_id}/results[?tag=]` | Metrics per variant with `n_effective` and `n_excluded`, and the corpus and QA snapshots they were measured on |
| `GET …/runs/{run_id}/results.csv` | The same as CSV, one row per variant and metric |
| `GET …/runs/{run_id}/questions[?limit=&offset=]` | The questions of the run with each variant's first-repetition outcome |
| `GET …/runs/{run_id}/questions/{question_id}` | Drill-down: every variant's executions and hits (rank, score, file, page, text, relevance), and the gold documents |

## Dependencies

Depends on `qa_sets`, `corpora`, `indexes`, `pipelines` and `retrieval`. `retrieval` depends
back on `experiments.repository` only to record the calls of an execution. The worker's
`temporal/activities/experiments.py` calls the services here.
