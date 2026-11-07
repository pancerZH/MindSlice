"""Address parsing, card-path validation and reference resolution.

Addresses come in two forms:

* namespace-qualified: ``@alias/relative/path``
* unqualified / slice-relative: ``relative/path``

When an unqualified reference is written *inside a card* (``extends``,
``supersedes`` or an inline ``[[wikilink]]``) it resolves strictly within the
card's own slice, never through global precedence (design section 3.2).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from .errors import InvalidAddressError

_ALIAS_RE = re.compile(r"^@[A-Za-z0-9][A-Za-z0-9_.-]*$")
_SEGMENT_RE = re.compile(r"^[\w][\w .-]*$", re.UNICODE)


def normalize_alias(alias: str) -> str:
    alias = (alias or "").strip()
    if not alias.startswith("@"):
        alias = "@" + alias
    if not _ALIAS_RE.match(alias):
        raise InvalidAddressError(f"invalid mount alias: {alias!r} (expected @name using letters, digits, '_', '.', '-')")
    return alias


def normalize_path(path: str) -> str:
    """Normalize a slice-relative card path (POSIX separators, no ``.md``)."""
    raw = path
    path = (path or "").strip().replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    path = path.strip("/")
    if path.endswith(".md"):
        path = path[:-3]
    segments = [s for s in path.split("/") if s not in ("",)]
    if not segments:
        raise InvalidAddressError(f"empty card path: {raw!r}")
    for seg in segments:
        if seg in (".", ".."):
            raise InvalidAddressError(f"card path may not contain '.' or '..' segments: {raw!r}")
        if seg.startswith(".") or not _SEGMENT_RE.match(seg) or seg != seg.strip():
            raise InvalidAddressError(
                f"invalid card path segment {seg!r} in {raw!r} (use letters, digits, '_', '-', '.', spaces; no leading dot)"
            )
    return "/".join(segments)


def parse_address(address: str) -> tuple[str | None, str]:
    """Split ``@alias/path`` into ``(alias, path)``; unqualified paths give ``(None, path)``."""
    if not isinstance(address, str):
        raise InvalidAddressError(f"address must be a string, got {type(address).__name__}")
    address = address.strip()
    if address.startswith("@"):
        alias, sep, rest = address.partition("/")
        if not sep or not rest.strip("/"):
            raise InvalidAddressError(f"qualified address needs a path after the alias: {address!r}")
        return normalize_alias(alias), normalize_path(rest)
    return None, normalize_path(address)


def format_address(alias: str, path: str) -> str:
    return f"{alias}/{path}"


# ---------------------------------------------------------------------------
# Wikilinks
# ---------------------------------------------------------------------------

WIKILINK_RE = re.compile(r"\[\[([^\[\]\|\n]+?)(\|[^\[\]\n]*)?\]\]")
_FENCE_RE = re.compile(r"^(\s*)(`{3,}|~{3,})")
_INLINE_CODE_RE = re.compile(r"(`+)(?:(?!\1).)+?\1")


def _code_mask(text: str) -> list[tuple[int, int]]:
    """Return character spans that are inside fenced code blocks or inline code."""
    spans: list[tuple[int, int]] = []
    pos = 0
    fence: str | None = None
    fence_start = 0
    for line in text.splitlines(keepends=True):
        m = _FENCE_RE.match(line)
        if fence is None and m:
            fence = m.group(2)[0] * 3
            fence_start = pos
        elif fence is not None and m and m.group(2).startswith(fence):
            spans.append((fence_start, pos + len(line)))
            fence = None
        elif fence is None:
            for im in _INLINE_CODE_RE.finditer(line):
                spans.append((pos + im.start(), pos + im.end()))
        pos += len(line)
    if fence is not None:
        spans.append((fence_start, len(text)))
    return spans


def _in_spans(idx: int, spans: list[tuple[int, int]]) -> bool:
    return any(a <= idx < b for a, b in spans)


@dataclass(frozen=True)
class WikiLink:
    target: str  # raw target text (stripped, ``#anchor`` removed)
    start: int
    end: int
    label: str | None = None
    anchor: str | None = None


def extract_wikilinks(text: str) -> list[WikiLink]:
    """Extract ``[[target]]``, ``[[target|label]]`` and ``[[target#anchor]]`` links outside code."""
    spans = _code_mask(text)
    links: list[WikiLink] = []
    for m in WIKILINK_RE.finditer(text):
        if _in_spans(m.start(), spans):
            continue
        inner = m.group(1).strip()
        target, _, anchor = inner.partition("#")
        target = target.strip()
        if not target:
            continue
        label = m.group(2)[1:] if m.group(2) else None
        links.append(WikiLink(target=target, start=m.start(), end=m.end(), label=label, anchor=anchor or None))
    return links


def rewrite_wikilinks(text: str, mapping: dict[str, str]) -> str:
    """Rewrite link targets (raw target -> new target), preserving labels and anchors."""
    if not mapping:
        return text
    out: list[str] = []
    last = 0
    for link in extract_wikilinks(text):
        if link.target not in mapping:
            continue
        new = mapping[link.target]
        out.append(text[last : link.start])
        inner = new + (f"#{link.anchor}" if link.anchor else "") + (f"|{link.label}" if link.label is not None else "")
        out.append(f"[[{inner}]]")
        last = link.end
    out.append(text[last:])
    return "".join(out)


# ---------------------------------------------------------------------------
# Reference resolution over an in-memory catalog
# ---------------------------------------------------------------------------


@dataclass
class MountCatalog:
    """Paths and card aliases present in one mount (used for reference resolution)."""

    paths: set[str] = field(default_factory=set)
    aliases: dict[str, str] = field(default_factory=dict)  # lowercased alias -> path

    def add(self, path: str, aliases: Iterable[str] = ()) -> None:
        self.paths.add(path)
        for a in aliases:
            key = a.strip().lower()
            if key and key not in self.aliases:
                self.aliases[key] = path

    def remove(self, path: str) -> None:
        self.paths.discard(path)
        for key in [k for k, v in self.aliases.items() if v == path]:
            del self.aliases[key]

    def lookup(self, ref: str) -> str | None:
        """Resolve a slice-relative ref by exact path first, then by card alias."""
        try:
            path = normalize_path(ref)
        except InvalidAddressError:
            path = None
        if path is not None and path in self.paths:
            return path
        return self.aliases.get(ref.strip().lower()) or (self.aliases.get(path.lower()) if path else None)


@dataclass(frozen=True)
class Resolution:
    raw: str
    mount: str | None  # target mount alias (None when the ref is syntactically invalid)
    path: str | None  # canonical target path (or the intended path when unresolved)
    resolved: bool

    @property
    def address(self) -> str | None:
        if self.mount and self.path:
            return format_address(self.mount, self.path)
        return None


def resolve_ref(ref: str, src_mount: str, catalogs: dict[str, MountCatalog]) -> Resolution:
    """Resolve a reference written inside a card that lives in ``src_mount``."""
    ref = (ref or "").strip()
    if ref.startswith("@"):
        alias, _, rest = ref.partition("/")
        try:
            alias = normalize_alias(alias)
        except InvalidAddressError:
            return Resolution(ref, None, None, False)
        cat = catalogs.get(alias)
        if not rest:
            return Resolution(ref, alias, None, False)
        if cat is not None:
            hit = cat.lookup(rest)
            if hit is not None:
                return Resolution(ref, alias, hit, True)
        try:
            intended = normalize_path(rest)
        except InvalidAddressError:
            intended = None
        return Resolution(ref, alias, intended, False)
    cat = catalogs.get(src_mount)
    if cat is not None:
        hit = cat.lookup(ref)
        if hit is not None:
            return Resolution(ref, src_mount, hit, True)
    try:
        intended = normalize_path(ref)
    except InvalidAddressError:
        return Resolution(ref, src_mount, None, False)
    return Resolution(ref, src_mount, intended, False)
