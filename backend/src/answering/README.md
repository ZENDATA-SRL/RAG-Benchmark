# answering

The builtin **answer systems** and what they share. Not a domain module with routes: the
worker runs a system for one execution through `experiments.answering.AnswerRunner`.

| File | Role |
|---|---|
| `contracts.py` | `AnswerSystem` protocol, `AnswerResult` (`answer`, `refused`, `citations` as chunk ids, `usage`, `timings`, `error`), `Retrieve` |
| `rag_simple.py` | `RagSimple`, the implementation of `answer_system/rag_simple` |
| `chat_models.py` | `resolve_chat_model` (`ChatOpenAI` or `ChatBedrockConverse`), `missing_credentials`, `is_output_error` |
| `registry.py` | `BUILTIN_ANSWER_SYSTEMS`, keyed like the descriptors in `components/builtin` |
| `availability.py` | `sync_answer_system_availability`, run by the worker at startup |
| `exceptions.py` | Errors, permanent or transient (below) |

## The interface

`answer(question, config, retrieve) -> AnswerResult`: `config` is the answer profile's
`params`, `retrieve` is `RetrievalService.search` bound to the variant's index build and
retrieval profile and to the execution, so every search the system makes is recorded as a
call of the execution, as in a retrieval experiment. The result has the shape an external
system would return over HTTP, so both are recorded and scored by the same code.

## rag_simple

One search with the question as it is; **every** hit goes in the prompt as a numbered
passage (`[1] (file, page n)` and the text): how many is the retrieval profile's top-k, so
what was retrieved and what the model read are the same chunks. The model answers with
structured output `{answer, refused, cited_sources}`; the passage numbers are translated to
chunk ids, once each, in the order given. A passage whose chunk no longer exists is left out
of the citations.

`usage` is `{model, input_tokens, output_tokens}`, with the model the provider reports;
`timings` is `{retrieval_ms, model_ms, total_ms, retrieval: {embed_ms, search_ms, enrich_ms,
total_ms}}`.

## Errors

| Error | Kind | Effect on the execution |
|---|---|---|
| `AnswerOutputError` | permanent | answer not in the expected shape (unparsable, truncated, filtered) or citing a passage outside the prompt: the execution fails, no retry |
| `AnswerSystemUnavailableError` | permanent | the profile's provider has no credentials in the worker: the execution fails with the reason |
| `AnswerProviderError` | transient | network, rate limit, server error: raised for the workflow to retry with backoff. The chat client itself does not retry, so the backoff is the workflow's |

## Credentials

Read from the worker's environment, never from the profile: `OPENAI_API_KEY` for `openai`,
the AWS chain (variables, then the profile of a mounted `~/.aws`) for `bedrock`. At startup
the worker marks each builtin answer system available when at least one of its providers
has credentials, or unavailable with the missing ones as the reason.
