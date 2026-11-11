"""CLI shorthand only; persisted card references and the Python/MCP APIs keep their own scopes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .addressing import format_address, normalize_alias, normalize_path, parse_address
from .errors import AmbiguousAddressError, InvalidAddressError

if TYPE_CHECKING:  # pragma: no cover
    from .workspace import Workspace


def reference(ws: "Workspace", value: str, *, source: str | None = None) -> str:
    """Normalize a CLI reference under the caller's workspace lock.

    ``source=None`` is a global read; lineage arguments to write use the overlay as source.
    ``./path`` explicitly chooses the relative interpretation. An existing ``alias/path`` target
    is qualified only when no relative target also exists in that operation's scope.
    """
    raw = value.strip()
    if raw.startswith("@"):
        alias, path = parse_address(raw)
        return format_address(alias, path)
    if raw.startswith(("./", ".\\")):
        return normalize_path(raw)
    head, sep, tail = raw.partition("/")
    if not sep:
        return raw
    try:
        alias = normalize_alias(head)
    except InvalidAddressError:
        return raw
    cats = ws.index.catalogs()
    target = cats[alias].lookup(tail) if alias in cats else None
    if target is None:
        return raw
    path = normalize_path(raw)
    if source is None:
        local = ws.index.cards_at_path(path) or ws.index.cards_with_alias(path)
        relative = [format_address(r["mount"], r["path"]) for r in local]
    else:
        local = cats[source].lookup(raw) if source in cats else None
        relative = [format_address(source, local)] if local is not None else []
    qualified = format_address(alias, target)
    if relative:
        raise AmbiguousAddressError(
            f"{value!r} matches both a relative card and {qualified}; "
            f"use {qualified!r} for the mount or {'./' + raw!r} for the relative path",
            address=value, qualified=qualified, relative=relative,
        )
    return qualified
