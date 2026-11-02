from __future__ import annotations

from src.core.exceptions import DomainError, NotFoundError, ValidationError


class AnswerProfileError(DomainError):
    """Base class for errors on answer profiles."""

    code = "answer_profile_error"


class AnswerProfileNotFoundError(NotFoundError, AnswerProfileError):
    """Raised when a referenced answer profile does not exist."""

    code = "answer_profile_not_found"

    def __init__(self, profile_id: object) -> None:
        super().__init__(
            f"answer profile not found: {profile_id}",
            details={"answer_profile_id": str(profile_id)},
        )
        self.profile_id = profile_id


class NotAnAnswerSystemError(ValidationError, AnswerProfileError):
    """Raised when an answer profile is asked for on a component of another type."""

    code = "not_an_answer_system"

    def __init__(self, component_version_id: object, component_type: str) -> None:
        super().__init__(
            f"component version {component_version_id} is a {component_type}, "
            "not an answer_system",
            details={
                "component_version_id": str(component_version_id),
                "component_type": component_type,
            },
        )


class AnswerSystemNotAvailableError(ValidationError, AnswerProfileError):
    """Raised when the answer system cannot be executed, with the registry's reason."""

    code = "answer_system_not_available"

    def __init__(self, component_version_id: object, reason: str | None) -> None:
        super().__init__(
            f"answer system {component_version_id} is not available: "
            f"{reason or 'no reason given'}",
            details={
                "component_version_id": str(component_version_id),
                "reason": reason,
            },
        )


class InvalidParentProfileError(ValidationError, AnswerProfileError):
    """Raised when the parent profile is built on another component version.

    The differences from the parent are only meaningful between parameters of the same
    implementation.
    """

    code = "invalid_parent_profile"

    def __init__(self, parent_profile_id: object) -> None:
        super().__init__(
            f"parent profile {parent_profile_id} is on another component version",
            details={"parent_profile_id": str(parent_profile_id)},
        )
