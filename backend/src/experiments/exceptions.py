from __future__ import annotations

from typing import Any

from src.core.exceptions import (
    ConflictError,
    DomainError,
    NotFoundError,
    ValidationError,
)


class ExperimentError(DomainError):
    """Base class for experiment domain errors."""

    code = "experiment_error"


class ExperimentNotFoundError(NotFoundError, ExperimentError):
    """Raised when an experiment does not exist."""

    code = "experiment_not_found"

    def __init__(self, experiment_id: object) -> None:
        super().__init__(
            f"experiment not found: {experiment_id}",
            details={"experiment_id": str(experiment_id)},
        )
        self.experiment_id = experiment_id


class RunNotFoundError(NotFoundError, ExperimentError):
    """Raised when a run does not exist or belongs to another experiment."""

    code = "run_not_found"

    def __init__(self, run_id: object) -> None:
        super().__init__(f"run not found: {run_id}", details={"run_id": str(run_id)})
        self.run_id = run_id


class ExecutionNotFoundError(NotFoundError, ExperimentError):
    """Raised when a retrieval call is attributed to an execution that does not exist."""

    code = "execution_not_found"

    def __init__(self, execution_id: object) -> None:
        super().__init__(
            f"execution not found: {execution_id}",
            details={"execution_id": str(execution_id)},
        )
        self.execution_id = execution_id


class QuestionNotInRunError(NotFoundError, ExperimentError):
    """Raised when a drill-down asks for a question the run did not evaluate."""

    code = "question_not_in_run"

    def __init__(self, run_id: object, question_id: object) -> None:
        super().__init__(
            f"question {question_id} is not part of run {run_id}",
            details={"run_id": str(run_id), "question_id": str(question_id)},
        )


class VariantsOutsideSnapshotError(ValidationError, ExperimentError):
    """Raised when a variant searches an index built on another corpus snapshot.

    Variants of one experiment must search the same documents: otherwise one cannot tell
    whether a difference comes from the configuration or from the size of the search space.
    """

    code = "variants_outside_snapshot"

    def __init__(
        self, corpus_snapshot_id: object, offending: list[dict[str, Any]]
    ) -> None:
        names = ", ".join(str(item["name"]) for item in offending)
        super().__init__(
            f"variants built on a different corpus snapshot than {corpus_snapshot_id}: {names}",
            details={
                "corpus_snapshot_id": str(corpus_snapshot_id),
                "variants": offending,
            },
        )


class GoldCoverageChoiceRequiredError(ValidationError, ExperimentError):
    """Raised when some questions have gold documents missing from the corpus snapshot.

    Left alone, such questions would be counted as retrieval failures, which they are not:
    the answer is not in the search space. The caller must choose explicitly how to treat
    them, so the choice is visible and not a silent default.
    """

    code = "gold_coverage_choice_required"

    def __init__(self, uncovered: list[dict[str, Any]]) -> None:
        super().__init__(
            f"{len(uncovered)} question(s) have gold documents outside the corpus snapshot: "
            "exclude them from the metrics (uncovered_policy='exclude') or widen the snapshot",
            details={"uncovered_questions": uncovered, "options": ["exclude"]},
        )
        self.uncovered = uncovered


class MultipleBaselinesError(ValidationError, ExperimentError):
    """Raised when more than one variant is marked as the baseline."""

    code = "multiple_baselines"

    def __init__(self, names: list[str]) -> None:
        super().__init__(
            f"only one variant can be the baseline, got: {', '.join(names)}",
            details={"variants": names},
        )


class RunNotCancellableError(ConflictError, ExperimentError):
    """Raised when cancellation is requested on a run that already finished."""

    code = "run_not_cancellable"

    def __init__(self, run_id: object, status: object) -> None:
        super().__init__(
            f"run {run_id} is not running (status={status})",
            details={"run_id": str(run_id), "status": str(status)},
        )


class RunNotResumableError(ConflictError, ExperimentError):
    """Raised when a run cannot be relaunched: it is still running, or nothing is left to do."""

    code = "run_not_resumable"

    def __init__(self, run_id: object, reason: str) -> None:
        super().__init__(
            f"run {run_id} cannot be resumed: {reason}",
            details={"run_id": str(run_id), "reason": reason},
        )


class RunInProgressError(ConflictError, ExperimentError):
    """Raised when a run is re-evaluated while its executions are still being written."""

    code = "run_in_progress"

    def __init__(self, run_id: object, status: object) -> None:
        super().__init__(
            f"run {run_id} is still in progress (status={status}): evaluate it once it ends",
            details={"run_id": str(run_id), "status": str(status)},
        )
