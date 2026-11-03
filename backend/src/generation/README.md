# generation

Fills a QA set **without importing questions**. An agent reads the documents of the set's
origin corpus in the chunks of one chunking configuration and proposes questions, each with
its expected answer and the chunks that hold it, quoting a passage of every chunk it cites.
A job only proposes: a question enters the set, with confirmed evidence, when a person
accepts it in the review queue.

## What a job asks

- `per_document`: questions for each document, answered by chunks of that document;
- `cross_document`: questions whose answer needs chunks of two or three documents.

Plus the configuration, the documents to read (`document_ids`, by default all of the
corpus) and those to leave out, `provider`
(`openai`, `bedrock`), `model`, `region`, `temperature`, `language` (default: the
documents'), a free `instructions` for the generator ("questions a help desk operator would
ask") and `max_steps` (model calls per unit, default 40). All are saved on the job in
`params`, with the limits of the checks and the `prompt_version`.

## Entities (`models.py`)

| Entity | Role |
|---|---|
| `GenerationJob` | QA set, chunking configuration, `document_ids` (the order the short references follow), `params`, `prompt_version`, `status` (`pending`, `running`, `completed`, `failed`, `cancelled`), `progress`, `workflow_id`, `error` |
| `GenerationUnit` | One run of the agent with a `target`: `phase` (`document` with its `document_id`, or `cross`), `position`, `produced`, `status`, `summary` and `topics` (document phase), `discards` by reason, `end_reason`, `error`, `langfuse_trace_id`. The unit of resume |
| `GeneratedQuestion` | A proposal: `kind` (`single`, `multi`, `cross`), `text` and `answer` as the agent wrote them, `status` (`pending`, `accepted`, `rejected`), `accepted_question_id`, `reviewed_by`, `reviewed_at` |
| `GeneratedQuestionChunk` | A chunk a proposal cites, with its document, `relevance`, the `quote` and its rank |

## Creating a job (`GenerationService.plan`, `create`)

The documents are those of the set's origin corpus, or only those in `document_ids` (a
question or a few on one document, or across two or three chosen documents, without
leaving out the rest one by one), without `excluded_document_ids`; they keep the order of
the corpus. A chosen document outside the corpus is `422 documents_outside_corpus`. A set
without an origin corpus cannot generate (`422 qa_set_without_corpus`). A document without
ready chunks or parsed text in the configuration gives the agent nothing to read, so the
job is refused with the list (`422 unmaterialized_documents_choice_required`) unless
`exclude_unmaterialized: true` leaves them out (`excluded` in the response). `422
nothing_to_generate` when no question is asked or no document is left, `422
cross_needs_two_documents` for cross questions over one document.

`POST /generation-jobs/estimate` runs the same checks without creating anything and returns
what the job would cost at most (units per document, cross units, steps per unit, model
calls) and the documents of the corpus with whether each can be read, for the dialog.

The job is created with its units: one per document with target `per_document`, then the
cross questions in units of at most 5.

## Generation (`runner.py`, `agent.py`, `tools.py`, `prompts.py`)

The worker's `GenerateQuestionsWorkflow` runs the **document phase** first, units in
parallel with bounded concurrency, then the **cross phase**, units one after the other.
Each unit is one `create_agent` run (`langchain`) with the chat model from
`answering.chat_models.resolve_chat_model` and the tools below, bound to its perimeter: the
unit's document in the document phase, all the job's documents in the cross phase.

Documents and chunks have short references, `d3` and `d3:c41` (document 3 of the job,
chunk ordinal 41), derived from what they are (`refs.py`): the model never copies a UUID,
and a chunk has the same reference in every unit.

| Tool | Returns |
|---|---|
| `list_documents(offset)` | reference, file name, `path` (empty for now), text length, chunk count, the summary and topics of the document phase or else the opening words; 20 per page |
| `read_document(doc, offset, max_chars ≤ 6000)` | a window of the parsed text, with its total length and the next offset |
| `document_outline(doc, offset)` | the chunks: reference, page, zone, first ~120 characters; 20 per page |
| `find_chunks(doc, passage)` | the chunks that contain a passage, compared after normalisation: the bridge from the text read to the chunk to cite |
| `read_chunk(chunk)`, `neighbours(chunk, n ≤ 3)` | the text of a chunk, and of the chunks around it |
| `search(query, docs?)` | the 5 chunks most relevant to a query, Postgres full text with the `simple` dictionary, any word, ranked by `ts_rank` (no index: a scan over the chunks of the documents) |
| `submit_question(question, answer, citations[{chunk, quote}])` | `saved`, or `discarded` with the reason |
| `finish(summary, topics)` | ends the run; in the document phase it records the summary and topics the cross phase reads |

Every tool cuts its output, since it stays in the agent's context, and every call
heartbeats the activity. The calls the model makes in one turn run one after the other:
they share the unit's database session, and a submission must see those before it to
catch a duplicate. No structured final answer is requested: what the agent produces
goes through the tools, which keeps the tool choice free on every turn (some Bedrock models
refuse a forced one).

**Prompt caching** (`agent.prompt_caching`). Every model call of a unit resends the system
prompt, the tools, the task and all the steps so far, so the provider is asked to reuse
that prefix. OpenAI caches long prefixes on its own: the calls carry `prompt_cache_key` set
to the unit id, so the calls of a unit, and its retries, reach the same cache. On Bedrock
`langchain-aws`'s `BedrockPromptCachingMiddleware` adds the `cachePoint` markers (5 minute
TTL) for the models that support them (Claude, Nova) and does nothing for the others.

**Variety.** In the document phase the chunks are split into `per_document` zones by
ordinal (`zones.py`), shown in the outline, and the prompt asks for about one question per
zone, otherwise the questions gather on the first pages. In the cross phase the prompt asks
for combinations and kinds of question that differ (comparison, complementary information,
exception, sequence), with the questions already delivered in context, and for a question
that really needs every document cited.

**Checks** (`verification.py`, pure), at submission, first failure wins, the reason going
back to the agent so it can fix and resubmit:

| Reason | When |
|---|---|
| `empty_field` | question, answer or citations empty |
| `unknown_chunk` | a reference that names no chunk the unit can read |
| `quote_not_in_chunk` | the quote is not found in the chunk it is given for after normalisation (`transfers/matching.py`), or is shorter than 5 words; it is never moved to another chunk |
| `outside_document` | document phase: a chunk of another document |
| `single_document`, `too_many_documents` | cross phase: fewer than 2 or more than 3 documents |
| `too_many_chunks` | more than 4 chunks |
| `duplicate` | word overlap ≥ 0.8, either way, with a current question of the set or a proposal of the job not rejected |

A question that passes is **saved at once, in its own transaction**. Kind and grades come
from the evidence: one chunk is `single` and `sufficient`; several chunks of one document
`multi`, several documents `cross`, all `supporting` (how the chunk metrics read evidence
without a sufficient chunk).

A unit ends when its target is reached (`target_reached`), when the agent calls `finish`
(`agent_finished`) or stops calling tools (`agent_stopped`), at the step limit
(`max_steps`) or on an answer the model got wrong (`invalid_output`); it then succeeds, and
a target not reached shows as `produced < target`. A provider failure is raised so the
workflow retries the unit with backoff: it restarts with the questions it saved in context
and only what is left of its target, so nothing is lost or duplicated. Missing credentials
fail the job when it opens on the worker, before any unit runs.

**Tracing**: one trace per unit, with an id derived from the unit; the root
`generate-questions` carries `generation_job_id`, `qa_set_id`, `chunking_configuration_id`,
`phase`, `document`, `model`, `prompt_version` and the tags `generation`, `phase:<phase>`.
The agent's steps are recorded by Langfuse's LangChain handler (`Tracer.langchain_callbacks`)
under it, and every submission adds a `verify` span with the outcome of the checks.

## Review (`ReviewService`)

The queue lists the proposals of a job in the order they were saved, by status and kind.
Accepting is one transaction: the question with the text and answer as corrected by the
reviewer, `answerable`, the tags `generated` and `generated:<kind>` (the kind read again
from the chunks kept), the primary expected answer; then `EvidenceService.put` with
`confirmed` and the chunks and grades kept, the same path as manual authoring, which checks
the chunks and derives the gold documents. A chunk outside the job's documents or
configuration is `422 chunks_outside_job`, a proposal already decided `409
generated_question_already_reviewed`, a text already in the set `409` from the questions.
The proposal keeps the text the agent wrote. Rejecting leaves no trace in the set.

The tags let the slicing by tag read the generated questions apart from those written by
hand, and each kind apart.

## A note on bias

Questions are written from the chunks of **one** configuration: a single chunk question is
contained, by construction, in a chunk of it, so that configuration starts favoured against
one with other boundaries, and the retriever is helped by the words the question shares with
the chunk it was written from. The prompt asks to paraphrase; the tags let the metrics of
generated questions be read apart; configurations are compared through the transfer of the
evidence (`transfers`) and the document-level metrics, which do not depend on the chunk
boundaries. The UI recalls this when a job is started.

## Routes

| Route | Purpose |
|---|---|
| `POST /generation-jobs/estimate` | Checks and cost of a job, and the documents of the corpus, without creating it |
| `POST /generation-jobs` | Create a job with its units and start its workflow (`202`) |
| `GET /generation-jobs[?qa_set_id=]`, `GET /generation-jobs/{id}` | Jobs with parameters, progress by phase, discards by reason, proposals by status and kind, documents covered and combinations used |
| `GET /generation-jobs/{id}/units` | The units: target, produced, status, end reason, summary, discards, trace link |
| `POST /generation-jobs/{id}/cancel`, `POST …/resume` | Stop (`409` once ended); relaunch the units not done (`409` if running or all done) |
| `GET /generation-jobs/{id}/proposals[?status=&kind=]` | The review queue |
| `GET /generated-questions/{id}[?kind=]` | A proposal opened for review, with the next one waiting (of that kind) |
| `POST /generated-questions/{id}/accept`, `POST …/reject` | Decide on a proposal |

## Dependencies

Depends on `qa_sets` (questions, evidence), `pipelines` (configurations), `artifacts`
(chunks and parsed text), `corpora`, `answering` (chat models), `transfers` (text
normalisation) and the tracer in `infrastructure`. The worker's
`temporal/activities/generation.py` calls `runner.py`.
