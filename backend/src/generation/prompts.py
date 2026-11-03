from __future__ import annotations

import dataclasses

# Saved on each job: a change to the wording below changes the questions, so it gets a
# new version and the jobs before it stay readable as what they were.
PROMPT_VERSION = "1"

_BASE = """\
You write questions for the evaluation of a retrieval system over a collection of \
documents. Each question must be answerable from the documents, and you must prove it: \
when you submit a question you cite the chunks that hold the answer, quoting from each \
chunk the passage that supports it.

How to work:
- Read before you write. Use read_document to read the text, document_outline to see \
the chunks, and find_chunks to learn which chunk holds a passage you read. Use \
read_chunk and neighbours to read a chunk and what surrounds it, and search to look for \
a topic.
- Submit one question at a time with submit_question. The platform checks it at once \
and answers "saved" or "discarded" with the reason: when a question is discarded, fix \
what the reason says and submit again.
- Each quote must be copied exactly from the chunk you cite, at least a few words long. \
Never quote from one chunk and cite another.
- Paraphrase: do not copy the wording of the passage into the question. Ask what a real \
person would ask, with their words, without naming the document or its sections.
- The answer must be complete and short, written from the cited chunks only.
- Do not repeat a question already saved, even with other words.
- When the target is reached, or there is nothing more worth asking, call finish.

Chunk references look like d1:c12 (document d1, chunk 12). Always use them as given."""

_DOCUMENT = """\
This run looks at one document only. Write {target} question(s) about it. Prefer \
questions whose answer is in a single chunk; a question that needs two or three chunks \
of the document is fine when the answer really spans them. The document is split in \
{zones} zone(s), shown in the outline: write about one question per zone, so the \
questions cover the whole document and not only its first pages.

When you call finish, give a summary of the document in two or three sentences and its \
main topics: they are shown later to whoever looks for questions spanning several \
documents."""

_CROSS = """\
This run looks at all the documents together. Write {target} question(s) whose answer \
needs chunks of at least {min_documents} and at most {max_documents} different documents: \
a comparison, two pieces of information that complete each other, an exception that one \
document makes to another, a sequence of steps across them. The answer must really need \
every cited document: not "what do A and B say about X". Vary the documents you combine \
and the kind of question. Start from the catalogue of the documents, with their summaries, \
to choose documents that are actually related."""


@dataclasses.dataclass(frozen=True)
class PromptOptions:
    """What the user asked of the generator, beyond the counts."""

    language: str | None
    instructions: str | None


def system_prompt(options: PromptOptions) -> str:
    """The instructions common to both phases, with the user's language and instruction."""
    parts = [_BASE]
    if options.language:
        parts.append(f"Write the questions and the answers in {options.language}.")
    else:
        parts.append(
            "Write the questions and the answers in the language of the documents."
        )
    if options.instructions:
        parts.append(
            f"Further instructions from the user: {options.instructions.strip()}"
        )
    return "\n\n".join(parts)


def document_task(
    *,
    target: int,
    zones: int,
    document: str,
    saved: list[str],
) -> str:
    """The request of a unit of the document phase, with what it already saved."""
    parts = [_DOCUMENT.format(target=target, zones=zones), document]
    parts.append(_saved(saved))
    return "\n\n".join(part for part in parts if part)


def cross_task(
    *,
    target: int,
    min_documents: int,
    max_documents: int,
    catalogue: str,
    delivered: list[str],
) -> str:
    """The request of a cross unit: the catalogue and the cross questions delivered so far."""
    parts = [
        _CROSS.format(
            target=target, min_documents=min_documents, max_documents=max_documents
        ),
        f"Catalogue of the documents:\n{catalogue}",
        _saved(delivered),
    ]
    return "\n\n".join(part for part in parts if part)


def _saved(questions: list[str]) -> str:
    if not questions:
        return ""
    lines = "\n".join(f"- {question}" for question in questions)
    return f"Questions already saved, not to be repeated:\n{lines}"
