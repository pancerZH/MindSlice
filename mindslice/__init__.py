"""MindSlice: a layered, pluggable, human-readable long-term memory engine for LLM agents.

Plain Markdown + TOML on disk is the single source of truth; ``.cache/index.sqlite``
is a disposable acceleration cache. Standard library only (Python 3.12+).

    >>> from mindslice import Workspace
    >>> ws = Workspace.init("workspace")
    >>> ws.write("user-preferences/tooling", summary="The user prefers uv.", content="- Use `uv run` for scripts.")
    >>> ws.search("uv scripts")["results"][0]["address"]
    '@overlay/user-preferences/tooling'
"""

from .errors import (
    AlreadyExistsError,
    ApplyConflictError,
    BakeConflictError,
    FrontmatterError,
    InvalidAddressError,
    LineageCycleError,
    LockTimeoutError,
    MindSliceError,
    MountError,
    NotFoundError,
    PreconditionFailedError,
    ReadOnlyMountError,
    UnresolvedExportDependencyError,
    WorkspaceNotFoundError,
)
from .workspace import Workspace

__version__ = "0.1.0"

__all__ = [
    "Workspace",
    "MindSliceError",
    "AlreadyExistsError",
    "ApplyConflictError",
    "BakeConflictError",
    "FrontmatterError",
    "InvalidAddressError",
    "LineageCycleError",
    "LockTimeoutError",
    "MountError",
    "NotFoundError",
    "PreconditionFailedError",
    "ReadOnlyMountError",
    "UnresolvedExportDependencyError",
    "WorkspaceNotFoundError",
    "__version__",
]
