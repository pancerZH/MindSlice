"""Minimal, verified TOML v1.0 serializer for MindSlice's flat schemas.

``tomllib`` only parses, so MindSlice ships its own writer for the two shapes
it emits: card frontmatter (``str`` / ``list[str]`` values) and manifests such
as ``mounts.toml`` / ``slice.toml`` (which additionally use ``int`` / ``bool``
values and tables).

Strings are emitted as UTF-8 directly (never as UTF-16 surrogate escapes the
way ``json.dumps`` would), with the TOML short escapes for ``\\ \" \\b \\t \\n
\\f \\r`` and 4-digit ``\\uXXXX`` scalars for the remaining control characters
(U+0000-U+001F, U+007F). Every document produced here is re-parsed with
``tomllib.loads()`` and compared against its input before it is returned.
"""

from __future__ import annotations

import re
import tomllib
from typing import Any, Mapping

from .errors import FrontmatterError

_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")
_SHORT_ESCAPES = {
    "\\": "\\\\",
    '"': '\\"',
    "\b": "\\b",
    "\t": "\\t",
    "\n": "\\n",
    "\f": "\\f",
    "\r": "\\r",
}


def escape_string(value: str) -> str:
    """Return ``value`` as a TOML basic string literal (including quotes)."""
    out = ['"']
    for ch in value:
        code = ord(ch)
        if ch in _SHORT_ESCAPES:
            out.append(_SHORT_ESCAPES[ch])
        elif code < 0x20 or code == 0x7F:
            out.append(f"\\u{code:04X}")
        elif 0xD800 <= code <= 0xDFFF:
            raise FrontmatterError(f"lone UTF-16 surrogate U+{code:04X} cannot be encoded in TOML")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def format_key(key: str) -> str:
    if not isinstance(key, str) or not key:
        raise FrontmatterError(f"invalid TOML key: {key!r}")
    return key if _BARE_KEY.match(key) else escape_string(key)


def format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return escape_string(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(format_value(v) for v in value) + "]"
    raise FrontmatterError(f"unsupported TOML value type: {type(value).__name__}")


def _verify(text: str, expected: Mapping[str, Any]) -> str:
    try:
        parsed = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:  # pragma: no cover - defensive
        raise FrontmatterError(f"serializer produced invalid TOML: {exc}") from exc
    if parsed != _normalize(expected):
        raise FrontmatterError("TOML round-trip verification failed")
    return text


def _normalize(obj: Any) -> Any:
    if isinstance(obj, Mapping):
        return {k: _normalize(v) for k, v in obj.items()}
    if isinstance(obj, tuple):
        return [_normalize(v) for v in obj]
    if isinstance(obj, list):
        return [_normalize(v) for v in obj]
    return obj


def dumps_flat(data: Mapping[str, Any]) -> str:
    """Serialize a flat mapping of scalars / lists of scalars (card frontmatter)."""
    lines = []
    for key, value in data.items():
        if isinstance(value, Mapping):
            raise FrontmatterError(f"frontmatter key {key!r} must be flat (got a table)")
        lines.append(f"{format_key(key)} = {format_value(value)}")
    text = "\n".join(lines) + ("\n" if lines else "")
    return _verify(text, data)


def dumps_document(
    top: Mapping[str, Any] | None = None,
    tables: Mapping[str, Mapping[str, Any]] | None = None,
    array_tables: Mapping[str, list[Mapping[str, Any]]] | None = None,
    header: str | None = None,
) -> str:
    """Serialize a document made of top-level keys, ``[tables]`` and ``[[array tables]]``."""
    top = dict(top or {})
    tables = dict(tables or {})
    array_tables = dict(array_tables or {})
    chunks: list[str] = []
    if header:
        chunks.append("".join(f"# {line}\n" if line else "#\n" for line in header.splitlines()))
    if top:
        chunks.append("".join(f"{format_key(k)} = {format_value(v)}\n" for k, v in top.items()))
    for name, body in tables.items():
        lines = [f"[{format_key(name)}]"]
        lines += [f"{format_key(k)} = {format_value(v)}" for k, v in body.items()]
        chunks.append("\n".join(lines) + "\n")
    for name, items in array_tables.items():
        for body in items:
            lines = [f"[[{format_key(name)}]]"]
            lines += [f"{format_key(k)} = {format_value(v)}" for k, v in body.items()]
            chunks.append("\n".join(lines) + "\n")
    text = "\n".join(chunks)
    expected: dict[str, Any] = dict(top)
    expected.update({k: dict(v) for k, v in tables.items()})
    expected.update({k: [dict(i) for i in v] for k, v in array_tables.items() if v})
    return _verify(text, expected)
