from __future__ import annotations

from typing import Any

from src.core.exceptions import NotFoundError, UnsupportedOperationError, ValidationError


class ComponentNotFoundError(NotFoundError):
    """Raised when a component does not exist."""

    code = "component_not_found"

    def __init__(self, component_id: object) -> None:
        super().__init__(
            f"component not found: {component_id}",
            details={"component_id": str(component_id)},
        )
        self.component_id = component_id


class ComponentVersionNotFoundError(NotFoundError):
    """Raised when a component version does not exist."""

    code = "component_version_not_found"

    def __init__(self, version_id: object) -> None:
        super().__init__(
            f"component version not found: {version_id}",
            details={"component_version_id": str(version_id)},
        )
        self.version_id = version_id


class InvalidParamsSchemaError(ValidationError):
    """Raised when a version declares a `params_schema` that is not a valid JSON Schema.

    Checked at registration and not at first use: an unusable schema would otherwise
    surface as a broken form in the UI, far from the change that caused it.
    """

    code = "invalid_params_schema"

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"params_schema is not a valid JSON Schema: {reason}",
            details={"reason": reason},
        )
        self.reason = reason


class InvalidComponentParamsError(ValidationError):
    """Raised when a profile's parameters violate the version's declared JSON Schema."""

    code = "invalid_component_params"

    def __init__(self, field_path: str, reason: str) -> None:
        super().__init__(
            f"invalid parameter at {field_path or '<root>'}: {reason}",
            details={"field_path": field_path, "reason": reason},
        )
        self.field_path = field_path
        self.reason = reason


class UnsupportedRuntimeError(UnsupportedOperationError):
    """Raised when a version declares a runtime the MVP cannot execute.

    `http` exists in the data model so remote components need no migration later, but no
    client invokes it yet; accepting the row would let a user build a profile that fails
    only at materialisation time.
    """

    code = "unsupported_runtime"

    def __init__(self, runtime: object) -> None:
        # `str()` on a `(str, Enum)` member yields `RuntimeType.HTTP`; the wire contract
        # uses the value the client sent.
        name = getattr(runtime, "value", runtime)
        super().__init__(
            f"runtime not supported in this version: {name} (only 'builtin')",
            details={"runtime": str(name), "supported": ["builtin"]},
        )
        self.runtime = runtime


class UnknownBuiltinError(ValidationError):
    """Raised when a `builtin` version's key was never declared in the repository.

    A builtin is by definition code that ships with the application, so a key absent from
    `BUILTIN_KEYS` is a registration mistake. That the declared key is also *implemented*
    is asserted by the worker at startup, the only process able to tell.
    """

    code = "unknown_builtin"

    def __init__(self, component_type: Any, key: str) -> None:
        type_name = getattr(component_type, "value", component_type)
        super().__init__(
            f"no builtin implementation for {type_name}/{key}",
            details={"type": str(type_name), "key": key},
        )
        self.component_type = component_type
        self.key = key
