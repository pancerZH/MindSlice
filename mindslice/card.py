"""Memory-card parsing and serialization.

A card is a Markdown file with optional ``+++``-fenced TOML frontmatter::

    +++
    title = "..."
    aliases = [...]
    tags = [...]
    extends = []
    supersedes = []
    +++

    One or two sentence summary paragraph.

    - Atomic statement with a [[wikilink]].

Parsing is lenient (so the index can always make progress on hand-edited
files); strictness lives in ``validate()``. Serialization keeps untouched parts
of a card byte-for-byte so human formatting and TOML comments survive edits
that don't concern them.
"""

from __future__ import annotations

import hashlib
import re
import tomllib
from dataclasses import dataclass, field
from typing import Any, Iterable

from . import tomlfmt
from .addressing import extract_wikilinks
from .lexical import normalize
from .errors import FrontmatterError

FENCE = "+++"
KNOWN_FIELDS = ("title", "aliases", "tags", "extends", "supersedes")
LIST_FIELDS = ("aliases", "tags", "extends", "supersedes")
SUMMARY_PREVIEW_CHARS = 240
MAX_CARD_LINES = 50

_BLOCK_START_RE = re.compile(r"^(?:[-*+]\s|#|```|~~~|>|\||<|\d+[.)]\s|(?:-{3,}|\*{3,}|_{3,})\s*$|\+\+\+)")
_BULLET_RE = re.compile(r"^[-*+]\s+")
_NUMBERED_RE = re.compile(r"^\d+[.)]\s+")
_HEADING_RE = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$")
_WS_RE = re.compile(r"\s+")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_newlines(text: str) -> str:
    text = text.lstrip("﻿")
    return text.replace("\r\n", "\n").replace("\r", "\n")


@dataclass
class ParsedCard:
    """Structured view over a card's text."""

    frontmatter: dict[str, Any]
    raw_frontmatter: str | None  # text between the fences, or None when absent
    after: str  # everything after the closing fence line (or the whole text)
    summary: str
    body: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # -- typed accessors -------------------------------------------------
    @property
    def has_frontmatter(self) -> bool:
        return self.raw_frontmatter is not None

    def list_field(self, name: str) -> list[str]:
        value = self.frontmatter.get(name)
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [v for v in value if isinstance(v, str)]
        return []

    @property
    def title(self) -> str:
        value = self.frontmatter.get("title")
        return value if isinstance(value, str) else ""

    @property
    def aliases(self) -> list[str]:
        return self.list_field("aliases")

    @property
    def tags(self) -> list[str]:
        return self.list_field("tags")

    @property
    def extends(self) -> list[str]:
        return self.list_field("extends")

    @property
    def supersedes(self) -> list[str]:
        return self.list_field("supersedes")

    def wikilink_targets(self) -> list[str]:
        seen: dict[str, None] = {}
        for link in extract_wikilinks(self.after):
            seen.setdefault(link.target, None)
        return list(seen)

    def heading_title(self) -> str:
        for line in self.after.split("\n"):
            m = _HEADING_RE.match(line.strip())
            if m and line.lstrip().startswith("# "):
                return m.group(1).strip()
        return ""

    def display_title(self, path: str) -> str:
        if self.title.strip():
            return self.title.strip()
        heading = self.heading_title()
        if heading:
            return heading
        leaf = path.rsplit("/", 1)[-1]
        return leaf.replace("-", " ").replace("_", " ").strip().capitalize() or path


def split_frontmatter(text: str) -> tuple[str | None, str]:
    """Return ``(raw_frontmatter, after)``; ``raw_frontmatter`` is None when absent.

    Raises ``FrontmatterError`` when an opening fence has no closing fence.
    """
    text = normalize_newlines(text)
    first_nl = text.find("\n")
    first_line = text if first_nl < 0 else text[:first_nl]
    if first_line.rstrip() != FENCE:
        return None, text
    pos = len(text) if first_nl < 0 else first_nl + 1
    while pos < len(text):
        nl = text.find("\n", pos)
        line_end = len(text) if nl < 0 else nl
        if text[pos:line_end].rstrip() == FENCE:
            return text[first_nl + 1 : pos], ("" if nl < 0 else text[nl + 1 :])
        if nl < 0:
            break
        pos = nl + 1
    raise FrontmatterError("frontmatter opened with '+++' but never closed")


def split_summary(after: str) -> tuple[str, str]:
    """Split post-frontmatter text into ``(summary_paragraph, body)``."""
    lines = after.split("\n")
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines):
        return "", ""
    if _BLOCK_START_RE.match(lines[i].lstrip()) or lines[i].startswith(("    ", "\t")):
        return "", "\n".join(lines[i:])
    j = i
    while j < len(lines) and lines[j].strip():
        j += 1
    summary = "\n".join(line.strip() for line in lines[i:j]).strip()
    k = j
    while k < len(lines) and not lines[k].strip():
        k += 1
    return summary, "\n".join(lines[k:])


def parse_card(text: str) -> ParsedCard:
    """Parse card text leniently; problems are reported in ``errors`` / ``warnings``."""
    errors: list[str] = []
    warnings: list[str] = []
    try:
        raw_fm, after = split_frontmatter(text)
    except FrontmatterError as exc:
        errors.append(str(exc))
        raw_fm, after = None, normalize_newlines(text)
    frontmatter: dict[str, Any] = {}
    if raw_fm is not None:
        try:
            frontmatter = tomllib.loads(raw_fm)
        except tomllib.TOMLDecodeError as exc:
            errors.append(f"invalid TOML frontmatter: {exc}")
            frontmatter = {}
        errors.extend(schema_errors(frontmatter))
        for name in LIST_FIELDS:
            if isinstance(frontmatter.get(name), str):
                warnings.append(f"frontmatter field {name!r} should be a list of strings")
    summary, body = split_summary(after)
    return ParsedCard(frontmatter, raw_fm, after, summary, body, errors, warnings)


def schema_errors(frontmatter: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    for key, value in frontmatter.items():
        if isinstance(value, str):
            continue
        if isinstance(value, list) and all(isinstance(v, str) for v in value):
            if key == "title":
                errs.append("frontmatter field 'title' must be a string")
            continue
        errs.append(f"frontmatter field {key!r} must be a string or a list of strings (got {type(value).__name__})")
    return errs


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def ordered_frontmatter(fields: dict[str, Any]) -> dict[str, Any]:
    """Canonical key order: known fields first (always present), then extras in original order."""
    out: dict[str, Any] = {}
    out["title"] = fields.get("title") or ""
    for name in LIST_FIELDS:
        value = fields.get(name) or []
        if isinstance(value, str):
            value = [value]
        out[name] = list(value)
    for key, value in fields.items():
        if key not in out:
            out[key] = value
    errs = schema_errors(out)
    if errs:
        raise FrontmatterError("; ".join(errs))
    return out


def dump_frontmatter(fields: dict[str, Any]) -> str:
    return tomlfmt.dumps_flat(ordered_frontmatter(fields))


def compose_after(summary: str | None, body: str | None) -> str:
    chunks = []
    if summary and summary.strip():
        chunks.append(summary.strip())
    if body and body.strip():
        chunks.append("\n".join(line.rstrip() for line in body.strip("\n").split("\n")))
    return "\n\n".join(chunks) + "\n" if chunks else ""


def compose_card(fields: dict[str, Any], after: str) -> str:
    fm = dump_frontmatter(fields)
    after = after.lstrip("\n")
    text = f"{FENCE}\n{fm}{FENCE}\n"
    if after:
        text += "\n" + after
    if not text.endswith("\n"):
        text += "\n"
    return text


def render_card(fields: dict[str, Any], summary: str | None, body: str | None) -> str:
    return compose_card(fields, compose_after(summary, body))


# ---------------------------------------------------------------------------
# Bullet statements (append + dedupe)
# ---------------------------------------------------------------------------


def _norm_statement(block: str) -> str:
    first, *rest = block.split("\n")
    first = _BULLET_RE.sub("", first.strip(), count=1)
    return _WS_RE.sub(" ", normalize(" ".join([first] + [r.strip() for r in rest]))).strip().casefold()


def statement_blocks(content: str | Iterable[str]) -> list[str]:
    """Normalize caller content into ``- ...`` bullet blocks (continuation lines kept)."""
    items = [content] if isinstance(content, str) else [str(c) for c in content]
    blocks: list[str] = []
    for item in items:
        current_item_blocks: list[str] = []
        for line in normalize_newlines(item).split("\n"):
            if not line.strip():
                continue
            if line[:1] in (" ", "\t") and current_item_blocks:
                current_item_blocks[-1] += "\n" + line.rstrip()
                continue
            s = line.strip()
            if _BULLET_RE.match(s):
                s = "- " + _BULLET_RE.sub("", s, count=1)
            elif not _NUMBERED_RE.match(s):
                s = "- " + s
            current_item_blocks.append(s)
        blocks.extend(current_item_blocks)
    return blocks


def existing_statements(text: str) -> set[str]:
    out: set[str] = set()
    current: list[str] | None = None
    for line in text.split("\n"):
        if _BULLET_RE.match(line) or _NUMBERED_RE.match(line):
            if current:
                out.add(_norm_statement("\n".join(current)))
            current = [line]
        elif current is not None and line[:1] in (" ", "\t") and line.strip():
            current.append(line)
        else:
            if current:
                out.add(_norm_statement("\n".join(current)))
            current = None
    if current:
        out.add(_norm_statement("\n".join(current)))
    return out


def append_statements(after: str, blocks: list[str]) -> tuple[str, list[str]]:
    """Append bullet blocks not already present; returns ``(new_after, added_blocks)``."""
    seen = existing_statements(after)
    added: list[str] = []
    for block in blocks:
        key = _norm_statement(block)
        if key in seen:
            continue
        seen.add(key)
        added.append(block)
    if not added:
        return after, []
    base = after.rstrip()
    if not base.strip():
        return "\n" + "\n".join(added) + "\n", added
    last_para = base.split("\n\n")[-1]
    first_line = last_para.lstrip("\n").split("\n", 1)[0]
    sep = "\n" if (_BULLET_RE.match(first_line) or _NUMBERED_RE.match(first_line)) else "\n\n"
    return base + sep + "\n".join(added) + "\n", added


# ---------------------------------------------------------------------------
# Previews
# ---------------------------------------------------------------------------


def _strip_markup(line: str) -> str:
    line = _BULLET_RE.sub("", line.strip(), count=1)
    line = re.sub(r"^#{1,6}\s+", "", line)
    return line.strip()


def first_paragraph(text: str) -> str:
    """First run of prose lines, skipping headings, code fences, lists, quotes and tables."""
    in_fence = False
    collected: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
            if collected:
                break
            continue
        if in_fence:
            continue
        if not stripped:
            if collected:
                break
            continue
        if _BLOCK_START_RE.match(stripped):
            if collected:
                break
            continue
        collected.append(stripped)
    return " ".join(collected)


def preview_text(summary: str, body: str, limit: int = SUMMARY_PREVIEW_CHARS) -> tuple[str, bool]:
    """Return a whitespace-collapsed summary capped at ``limit`` chars plus a truncation flag."""
    text = summary.strip() or first_paragraph(body)
    if not text:
        for line in body.split("\n"):
            cleaned = _strip_markup(line)
            if cleaned and not cleaned.startswith(("```", "~~~", "|", "<")):
                text = cleaned
                break
    text = _WS_RE.sub(" ", text).strip()
    return truncate(text, limit)


def truncate(text: str, limit: int) -> tuple[str, bool]:
    if limit <= 0:
        return "", bool(text)
    if len(text) <= limit:
        return text, False
    cut = text[: limit - 1]
    space = cut.rfind(" ")
    if space >= limit * 0.6:
        cut = cut[:space]
    return cut.rstrip(" ,;:") + "…", True
