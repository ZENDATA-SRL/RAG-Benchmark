# answer_profiles

Configurations of an **answer system**: which system (a `component_versions` row of type
`answer_system`) and with which parameters (provider, model, system prompt, temperature,
...). A Q&A variant points at one; they are not a materialised pipeline stage.

| File | Role |
|---|---|
| `models.py` | `AnswerProfile`: `name`, `component_version_id`, `params`, `config_hash` (unique), `parent_profile_id` |
| `service.py` | `AnswerProfileService`: get-or-create on the hash, parent check, changed parameters, availability of the system |
| `repository.py` | Data access, keyed by `config_hash` |
| `router.py` | Routes below |
| `schemas.py`, `exceptions.py` | DTOs and errors |

## Identity

`config_hash = hash(component_version_id + params)`, with the schema's defaults written into
`params` first: leaving `temperature` out and giving `0` is the same profile. Everything that
changes the answers is a parameter, the system prompt included by value, so changing the
prompt or the model is a new profile and asking twice for the same configuration returns the
existing row (`created: false`). Credentials are never parameters: the worker reads them from
its environment.

The name is derived, never typed: `rag_simple@1 openai/gpt-4o-mini t=0`, with a short hash
suffix when two profiles differ only in something the name does not show, such as the
prompt.

`parent_profile_id` records the profile this one was derived from, on the same component
version (`422 invalid_parent_profile` otherwise). It is written only on creation and is
informative: removing the parent sets it to NULL.

## Routes

| Route | Purpose |
|---|---|
| `POST /answer-profiles` | `component_version_id`, `params`, optional `parent_profile_id`. `201` with `profile`, `created` and `detail`. `422` when the component is not an answer system (`not_an_answer_system`), the version is unavailable (`answer_system_not_available`, with the reason), or the parameters violate the schema (`invalid_component_params`) |
| `GET /answer-profiles[?component_version_id=]` | Page of profiles by name |
| `GET /answer-profiles/{id}` | One profile with `changed_params`: each parameter whose value differs from the parent's (`key`, `parent`, `value`) |

## Dependencies

Depends on `components`, `core` and `pipelines` (naming and the shared `DeduplicatedRead`).
`experiments` depends on it for the Q&A variants.
