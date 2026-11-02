# experiments

Experiments: a comparison of **variants** (index build x retrieval profile, x answer
profile for Q&A) on one corpus snapshot and one frozen question set, executed on Temporal
and measured at document level and, where the evidence is confirmed, at chunk level. The
**type** of the experiment decides how an execution runs and which metrics it is scored on
(see *Metrics*): `retrieval` measures the retriever, `qa` measures a whole answer system
that may search several times and answers.

## Entities (`models.py`)

| Entity | Role |
|---|---|
| `Experiment` | Type, corpus snapshot, QA snapshot, repetitions, `retrieval_scope` (`retrieved` or `cited`, read by Q&A only), `uncovered_policy`. The snapshot is repeated here although derivable from the variants: it is the guard that makes "every variant searches the same documents" checkable |
| `Variant` | Index build x retrieval profile, plus `answer_profile_id` (FK to `answer_profiles`) in a Q&A experiment and NULL in a retrieval one; one is the baseline (the first, if none is marked). Named after what it searches and how: configuration · embedder · vector store · retrieval profile, then the answer profile for Q&A, without the snapshot all variants share |
| `Run` | One execution, with `config_snapshot` (experiment, snapshots, variants, index builds and profiles **copied by value**, answer profiles included with their component, capabilities and parameters, and the evidence the chunk metrics were scored on), the denormalised `progress` the UI polls, and `error` |
| `Execution` | Question x variant x repetition, unique per run: the unit of idempotency and resume. In a Q&A run it holds the answer: `answer_text`, `refused`, `usage` (`model` as the provider reports it, `input_tokens`, `output_tokens`), `timings` (`retrieval_ms`, `model_ms`, `total_ms` and the search breakdown; a retrieval run has the search timings only). `cited_chunk_ids` holds what an answer system says it used: NULL when it declares no citations, empty when it cited nothing; it may name chunks no call retrieved, which is why it is here and not on the hits |
| `RetrievalCall`, `RetrievalHit` | One call of the retrieval tool and the chunks it returned, with rank, score, stage, `relevant_document` and `relevant_chunk`. The raw log: a chunk returned by two calls has two hits |
| `MetricDefinition`, `Evaluator`, `Evaluation` | The catalog of metrics (each with its family and level: `document`, `chunk`, or none for the call and answer metrics), the deterministic evaluators (one per level, one for the answer), and one score (or exclusion with its reason) per execution and metric |
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
3. **Answer profiles.** A `qa` experiment needs an `answer_profile_id` on every variant
   (`422 answer_profile_required`, listing the variant positions), on a system that is
   available (`422 answer_system_not_available` with the reason). A `retrieval` experiment
   takes no answer profile and only the `retrieved` scope (`422
   answer_profile_not_allowed`). `retrieval_scope: "cited"` needs every system to declare
   `supports_citations` (`422 citations_not_supported`).

To isolate the effect of the answer system, the variants of a Q&A experiment keep the same
index build and retrieval profile and differ only by the answer profile.

## Runs (`RunLauncher`, `RunService`)

`POST /experiments/{id}/runs` requires every variant's index build to be `ready`, creates
the run with its `config_snapshot` and every `pending` execution, and starts
`RunExperimentWorkflow` (id `run-experiment-{run_id}`, queue `experiments`). `concurrency`
(default 5) is the number of queries (or, for Q&A, answers) in flight, because query
embeddings and chat models are rate limited.

- `POST …/runs/{run_id}/cancel` cancels the workflow and marks the run `failed` with
  `error = "cancelled"`.
- `POST …/runs/{run_id}/resume` relaunches an interrupted or partly failed run under the
  same workflow id: executions that succeeded are skipped, the others are redone.
- A question that fails marks only its execution `failed` with the reason, and the run
  goes on; the run is `succeeded` when every execution was attempted, with the failures
  counted in `progress` and excluded from the metrics (`execution_failed`).

`ExecutionRunner` (in `evaluation.py`) is what the worker's activity calls for one
execution of a retrieval run: it runs `RetrievalService.search` in-process with the execution
id, which records the call and its hits, then scores the execution. A failure of the embedder
or the vector store is raised so the workflow retries it with backoff; any other domain error
fails the execution.

`AnswerRunner` (in `answering.py`) does the same for a Q&A run: it resolves the variant's
answer profile to its builtin system (see `src/answering`), hands it that same search bound
to the variant and the execution, so every search the system makes is recorded as a call,
writes the answer, `refused`, `usage`, `timings` and the cited chunks, then scores. A failure
of the model provider is retried like a failure of the embedder; an answer not in the
expected shape, a citation of a passage that was not in the prompt or a provider without
credentials fails the execution. Either way, what an attempt recorded is discarded before
the next one.

## Metrics (`metrics.py`, `evaluation.py`)

Computed per execution on its `final` hits, from the stored hits. Each metric declares in
`metrics.py` the experiment types it applies to, and an execution is scored only on those of
its experiment's type; a metric that does not apply has no evaluation at all, which is not
the same as an exclusion.

| Type | Metrics | Why |
|---|---|---|
| `retrieval` | ranked metrics only (the two tables below) | every execution makes one call: set metrics would repeat the ranked ones at the profile's top-k, and call metrics would be constants |
| `qa` | ranked metrics on the **first call**, set metrics on the experiment's scope, call metrics, answer metrics | a system may search several times; the columns are the same for every answer system, even one that searches once, so a simple chain and an agent compare |

The ranked metrics are always computed on the hits of the first call (the lowest
`call_index`): several calls give lists whose ranks and scores do not compare, and with one
call this is every hit. The cutoff k counts **retrieved chunks**, best first: `@5` judges the
first five chunks, which is what a generator would be given. The cutoffs are fixed and not
the profile's top-k, so `recall@5` means the same in every variant.

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
chunks. The metrics are shares of that evidence (or ranks of it), so they read as how well
the evidence was surfaced and compare across configurations, next to the number of questions
each rests on; the recall ceiling of each configuration says how much of the evidence
exists in its chunks. A chunk retrieved twice by one execution keeps its first rank and
counts once.

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

**Set metrics (Q&A).** On the **distinct** chunks of the experiment's scope, without cutoff:
`retrieved` is every chunk the calls returned, `cited` the execution's `cited_chunk_ids`, even
chunks never retrieved. A chunk retrieved twice is one chunk of the set: it is not twice the
evidence. They are always read next to the set size, since ten searches of five reach up to
fifty chunks and beat a top-5 without being a better retriever.

| Metric | Definition |
|---|---|
| `set_recall`, `set_precision` | gold documents reached by the set / gold documents; chunks of the set from a gold document / chunks of the set |
| `chunk_set_recall`, `chunk_set_precision` | evidence chunks in the set / evidence chunks; evidence chunks in the set / chunks of the set |
| `first_relevant_call_index`, `chunk_first_relevant_call_index` | position, from 1, of the first call that returned a chunk from a gold document (an evidence chunk); empty when none did |

**Call metrics (Q&A, family `efficiency`, no level).** On every hit, repetitions included:
repeated hits are wasted calls and context, and are measured rather than hidden in the set.

| Metric | Definition |
|---|---|
| `retrieval_call_count` | calls of the execution, those that returned nothing included |
| `retrieved_hit_count` | hits of every call |
| `retrieved_set_size` | distinct chunks retrieved |
| `duplicate_hit_rate` | `1 - retrieved_set_size / retrieved_hit_count`, 0 when nothing was retrieved |

A hit whose chunk is no longer known cannot be told a repeat: it counts as a distinct chunk
that is not relevant.

**Answer metrics (Q&A, no level, evaluator `answer_deterministic`).** Read from what the
execution recorded, never from the gold documents or the evidence, so they count every
question, the unanswerable ones included. Latency and tokens are aggregated like any metric,
so the results carry their median and p95 next to the mean.

| Metric | Family | Definition |
|---|---|---|
| `refusal_accuracy` | `answer` | 1 when the system refused exactly when the question is not answerable, 0 otherwise |
| `answer_latency_ms` | `efficiency` | `timings.total_ms`: searches and model |
| `model_latency_ms` | `efficiency` | `timings.model_ms` |
| `input_tokens`, `output_tokens` | `efficiency` | from `usage`, as the provider reports them |

**Exclusions.** Executions that do not count get an evaluation per metric with
`excluded = true` and the reason, and no score. At document level, in this order:
`not_answerable`, `no_gold_documents`, `gold_document_not_in_snapshot`, `execution_failed`.
At chunk level: `not_answerable`, then `evidence_not_reviewed` (no link under the
configuration, or a draft) and `evidence_not_found` (looked for and not among its chunks),
then `gold_document_not_in_snapshot` and `execution_failed`. A question can therefore count
for its documents and be left out for its chunks; a missing evidence is never scored 0. The
set metrics take the reasons of their level and, on the `cited` scope of an execution whose
system declared no citations, `scope_not_declared`: no citation says nothing about how well
a system attributes. The call metrics read no gold and are excluded only with
`execution_failed`. The answer metrics too, plus `not_reported` when the system did not
report the value (a missing token count is not zero); `refusal_accuracy` also leaves out a
question whose gold document is not in the snapshot (`gold_document_not_in_snapshot`), since
there refusing is the right answer and the label would score it wrong.

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
call is repeated), rewrites the aggregates and the record. It answers `202` and runs on the
worker as `EvaluateRunWorkflow` (id `evaluate-run-{run_id}-{n}`, `n` counting the run's
re-evaluations, queue `experiments`), in batches; `progress.evaluation` on the run holds
`status` (`running`, `succeeded`, `failed`), `evaluated`, `total`, `attempt` and `error`. It is
set `running` in the request itself, so a second request is refused before the workflow even
starts: `409 run_in_progress` while the run is pending or running, `409
evaluation_in_progress` while a re-evaluation is (resuming the run is refused the same way).
Scoring it twice on the same evidence gives the same numbers and the same fingerprint.

An experiment does not wait for the evidence to be complete: on a configuration whose
evidence is half reviewed, for instance during a transfer, the chunk metrics count the
confirmed questions and every other one is excluded with `evidence_not_reviewed` or
`evidence_not_found`, so the results say on how much they rest. The wizard shows the
evidence of each configuration of the chosen variants for the same reason.

`seed.py` registers the metric definitions with their family and the deterministic
evaluators (`document_level_retrieval`, `chunk_level_retrieval`,
`retrieval_call_efficiency` for the call metrics, which have no level, and
`answer_deterministic` for the answer metrics) at startup and again, idempotently, before
evaluating, so a worker never depends on the API having started. A re-evaluation re-scores
the answer metrics from the stored answers, without calling the model again.

## Results (`results.py`)

| Route | Purpose |
|---|---|
| `POST /experiments`, `GET /experiments[?qa_set_snapshot_id=]`, `GET /experiments/{id}` | Create (with the guards above; `type`, `retrieval_scope` and, per variant, `answer_profile_id`); list, optionally only the experiments run on one QA set snapshot; detail with variants (with `answer_profile_id` and `answer_profile_name`), runs and coverage. Both list and detail name the corpus and the QA set behind the two snapshots (`corpus_id`, `corpus_name`, `corpus_snapshot_label`, `qa_set_id`, `qa_set_name`, `qa_set_snapshot_label`) |
| `GET /experiments/coverage?corpus_snapshot_id=&qa_set_snapshot_id=` | The questions with gold documents outside a corpus snapshot |
| `GET /experiments/comparison?qa_set_snapshot_id=&type=` | The variants of every experiment of one type (`retrieval` or `qa`, which measure different things and are never mixed) on a QA set snapshot, flat: each with its experiment, the run it comes from (the experiment's latest finished one), the corpus snapshot, the chunking configuration with its `recall_ceiling`, and the same metrics as the results, with `n_effective`. Experiments without a finished run are listed in `skipped`. The baseline to measure against is chosen by the client |
| `POST /experiments/{id}/runs`, `GET …/runs/{run_id}` | Launch (`202`, `started=false` if already running); read a run with progress and configuration, served from the row |
| `POST …/runs/{run_id}/cancel`, `POST …/runs/{run_id}/resume` | See above |
| `POST …/runs/{run_id}/evaluate` | `202`: start re-scoring a finished run on the current evidence, on the worker; returns the run with `progress.evaluation` |
| `GET …/runs/{run_id}/results[?tag=]` | `experiment_type`; `groups`, one per chunking configuration (parser, chunker, `evidence_coverage`, `recall_ceiling`), each with its variants and their metrics (with `family`, `level`, `direction`, `aggregation` and a `description` of what it measures, taken from the metric catalog in code) with `n_effective`, `n_excluded` and `excluded_reasons`; `chunk_gold` gives the date and fingerprint of the evidence; and the corpus and QA snapshots |
| `GET …/runs/{run_id}/results.csv` | The same as CSV, one row per variant and metric, with the chunking configuration, the family and the level |
| `GET …/runs/{run_id}/questions[?limit=&offset=]` | The questions of the run with each variant's first-repetition outcome at both levels; in a Q&A run also each variant's `answer_text` and `refused`, and the question's primary `expected_answer` |
| `GET …/runs/{run_id}/answers.csv` | Every answer of the run, one row per question, variant and repetition, in snapshot order: the question, its tags, `answerable` and expected answer, the variant, status, `refused`, the answer, the number of cited chunks, model, tokens, total time and error. A retrieval run has the answer columns empty |
| `GET …/runs/{run_id}/questions/{question_id}` | Drill-down: the question's primary `expected_answer`; every variant's executions, each with `answer_text`, `refused`, `usage`, `timings`, its `calls` (query, hits, chunks no earlier call had), `citations_declared`, and `hits`: its distinct chunks in order of first retrieval (rank and score of the first time, file, page, text, `relevant_document`, `relevant_chunk` and its grade, `cited`, and `occurrences`: every call and rank it came back at), then the chunks cited and never retrieved (`retrieved = false`); the evidence status under its configuration and the evidence chunks, retrieved or not; the gold documents |

`recall_ceiling` is `1 - not_found / (confirmed + not_found)` on the evidence the run was
scored on: the share of the reviewed questions whose evidence exists among the chunks of the
configuration. It is a property of the configuration on the QA set, not of a variant, and
bounds what any variant of the group can reach on those questions.

## Dependencies

Depends on `qa_sets`, `corpora`, `indexes`, `pipelines`, `retrieval`, `answer_profiles` and
`answering`. `retrieval` depends
back on `experiments.repository` only to record the calls of an execution. The worker's
`temporal/activities/experiments.py` calls the services here.
