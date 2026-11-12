"""Exception hierarchy for MindSlice.

Every error carries a machine-readable ``code`` and an optional ``details``
payload so CLI and MCP front-ends can serialize failures as structured JSON.
"""

from __future__ import annotations

from typing import Any


class MindSliceError(Exception):
    """Base class for all MindSlice errors."""

    code = "mindslice_error"

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"error": type(self).__name__, "code": self.code, "message": self.message}
        if self.details:
            out["details"] = self.details
        return out


class WorkspaceNotFoundError(MindSliceError):
    code = "workspace_not_found"


class InvalidAddressError(MindSliceError, ValueError):
    code = "invalid_address"


class AmbiguousAddressError(InvalidAddressError):
    code = "ambiguous_address"


class NotFoundError(MindSliceError, LookupError):
    code = "not_found"


class AlreadyExistsError(MindSliceError):
    code = "already_exists"


class PreconditionFailedError(MindSliceError):
    """Raised when ``if_match`` does not match the current revision."""

    code = "precondition_failed"


class LineageCycleError(MindSliceError):
    code = "lineage_cycle"


class FrontmatterError(MindSliceError, ValueError):
    code = "invalid_frontmatter"


class ReadOnlyMountError(MindSliceError):
    code = "read_only_mount"


class MountError(MindSliceError):
    code = "mount_error"


class ApplyConflictError(MindSliceError):
    """Raised by ``apply()`` when staged preconditions or graph checks fail."""

    code = "apply_conflict"


class UnresolvedExportDependencyError(MindSliceError):
    code = "unresolved_export_dependency"


class BakeConflictError(MindSliceError):
    """Raised by ``bake()`` before writing anything, when a card can't move into the slice as it is."""

    code = "bake_conflict"


class InvalidArgumentsError(MindSliceError, ValueError):
    """A tool call's arguments don't fit the tool: a required one is missing, or one isn't in its schema."""

    code = "invalid_arguments"


class LockTimeoutError(MindSliceError, TimeoutError):
    code = "lock_timeout"


class HistoryError(MindSliceError):
    code = "history_error"


class RecoveryError(MindSliceError):
    """Recovery or backup cannot proceed without changing its reviewed scope."""

    code = "recovery_error"
