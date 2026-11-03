from __future__ import annotations

# The providers a job can name; the credentials are the worker's.
PROVIDERS = ("openai", "bedrock")

# Cross-document questions are asked in units of at most this many, run one after the
# other: the agent's context grows with every read, so several short runs keep each one
# cheap and sharp, and each sees the questions the previous ones delivered.
CROSS_BATCH = 5

# Model calls a unit may make: reading, locating the chunks and submitting take a few
# calls per question.
DEFAULT_MAX_STEPS = 40
MAX_MAX_STEPS = 200

# Units of the document phase run at once by the worker; each calls the chat model.
DEFAULT_CONCURRENCY = 4

DEFAULT_TEMPERATURE = 0.3
# Room for a tool call with a question, its answer and a few quotes.
DEFAULT_MAX_TOKENS = 2048

# How a unit ended, besides failing.
TARGET_REACHED = "target_reached"
AGENT_FINISHED = "agent_finished"
AGENT_STOPPED = "agent_stopped"
MAX_STEPS_REACHED = "max_steps"
INVALID_OUTPUT = "invalid_output"

# Tags of an accepted question: the generated ones can be measured apart from those
# written by hand, and by the shape of their evidence.
GENERATED_TAG = "generated"

TRACE_NAME = "generate-questions"
