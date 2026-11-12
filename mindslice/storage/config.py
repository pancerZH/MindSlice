"""``mounts.toml`` (workspace mount table) and ``slice.toml`` (slice manifest) handling."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..model import tomlfmt
from ..model.addressing import normalize_alias
from ..errors import MountError

MOUNTS_FILE = "mounts.toml"
SLICE_FILE = "slice.toml"
OVERVIEW_PATH = "overview"
DESCRIPTION_CHARS = 160

DEFAULT_OVERLAY = {"path": "./overlay", "alias": "@overlay", "precedence": 100, "role": "runtime"}

_MOUNTS_HEADER = (
    "MindSlice mount table.\n"
    "precedence only decides which mount wins for unqualified paths (and breaks exact score ties);\n"
    "role is opaque provenance metadata that callers may use as a trust policy (follow_supersedes)."
)


@dataclass(frozen=True)
class Mount:
    alias: str
    path: str  # as written in mounts.toml
    precedence: int
    role: str
    kind: str  # "overlay" | "slice"
    root: Path  # absolute, resolved directory

    @property
    def writable(self) -> bool:
        return self.kind == "overlay"

    def to_toml(self) -> dict[str, Any]:
        return {"path": self.path, "alias": self.alias, "precedence": self.precedence, "role": self.role}


@dataclass
class MountTable:
    overlay: Mount
    mounts: list[Mount] = field(default_factory=list)

    def all(self) -> list[Mount]:
        """All mounts, overlay included, ordered by precedence (desc) then alias."""
        return sorted([self.overlay, *self.mounts], key=lambda m: (-m.precedence, m.alias))

    def by_alias(self) -> dict[str, Mount]:
        return {m.alias: m for m in self.all()}

    def get(self, alias: str) -> Mount | None:
        return self.by_alias().get(alias)


def _resolve_root(workspace: Path, path: str) -> Path:
    p = Path(os.path.expanduser(path))
    if not p.is_absolute():
        p = workspace / p
    return Path(os.path.abspath(p))


def _int(value: Any, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise MountError(f"{what}: precedence must be an integer (got {value!r})")
    return value


def _mount_from(entry: dict[str, Any], workspace: Path, kind: str, what: str) -> Mount:
    if not isinstance(entry, dict):
        raise MountError(f"{what}: expected a table")
    path = entry.get("path")
    if not isinstance(path, str) or not path.strip():
        raise MountError(f"{what}: 'path' is required")
    alias = normalize_alias(str(entry.get("alias") or ""))
    role = entry.get("role", "runtime" if kind == "overlay" else "baseline")
    if not isinstance(role, str):
        raise MountError(f"{what}: role must be a string")
    precedence = _int(entry.get("precedence", 100 if kind == "overlay" else 50), what)
    return Mount(alias, path, precedence, role, kind, _resolve_root(workspace, path))


def load_mounts(workspace: Path) -> MountTable:
    path = workspace / MOUNTS_FILE
    data: dict[str, Any] = {}
    if path.exists():
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise MountError(f"{path}: invalid TOML: {exc}") from exc
    overlay_entry = dict(DEFAULT_OVERLAY)
    overlay_entry.update(data.get("overlay") or {})
    overlay = _mount_from(overlay_entry, workspace, "overlay", "[overlay]")
    mounts: list[Mount] = []
    seen = {overlay.alias}
    raw_mounts = data.get("mounts") or []
    if not isinstance(raw_mounts, list):
        raise MountError("mounts.toml: 'mounts' must be an array of tables ([[mounts]])")
    for i, entry in enumerate(raw_mounts):
        m = _mount_from(entry, workspace, "slice", f"[[mounts]] #{i + 1}")
        if m.alias in seen:
            raise MountError(f"mounts.toml: duplicate alias {m.alias}")
        seen.add(m.alias)
        mounts.append(m)
    return MountTable(overlay, mounts)


def dump_mounts(table: MountTable) -> str:
    return tomlfmt.dumps_document(
        tables={"overlay": table.overlay.to_toml()},
        array_tables={"mounts": [m.to_toml() for m in table.mounts]},
        header=_MOUNTS_HEADER,
    )


def save_mounts(workspace: Path, table: MountTable) -> str:
    from .fsutil import atomic_write_text

    text = dump_mounts(table)
    atomic_write_text(workspace / MOUNTS_FILE, text)
    return text


def portable_path(workspace: Path, target: Path) -> str:
    """Prefer ``./relative`` paths for mounts living inside the workspace."""
    target = Path(os.path.abspath(target))
    try:
        rel = target.relative_to(Path(os.path.abspath(workspace)))
    except ValueError:
        return str(target)
    return "./" + rel.as_posix() if rel.as_posix() != "." else "."


# ---------------------------------------------------------------------------
# slice.toml
# ---------------------------------------------------------------------------


@dataclass
class SliceManifest:
    name: str = ""
    version: str = ""
    description: str = ""
    alias: str = ""
    dependencies: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    present: bool = False

    def to_toml(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key in ("name", "version", "description", "alias"):
            value = getattr(self, key)
            if value:
                out[key] = value
        out["dependencies"] = list(self.dependencies)
        out.update(self.extra)
        return out


def load_slice_manifest(root: Path) -> SliceManifest:
    path = root / SLICE_FILE
    if not path.is_file():
        return SliceManifest()
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        return SliceManifest(errors=[f"invalid slice.toml: {exc}"], present=True)
    sm = SliceManifest(present=True)
    for key in ("name", "version", "description", "alias"):
        value = data.pop(key, "")
        if isinstance(value, str):
            setattr(sm, key, value)
        else:
            sm.errors.append(f"slice.toml: {key!r} must be a string")
    deps = data.pop("dependencies", [])
    if isinstance(deps, list) and all(isinstance(d, str) for d in deps):
        sm.dependencies = list(deps)
    else:
        sm.errors.append("slice.toml: 'dependencies' must be a list of strings")
    sm.extra = data
    return sm


def dump_slice_manifest(sm: SliceManifest) -> str:
    return tomlfmt.dumps_document(top=sm.to_toml())
