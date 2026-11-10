"""Memory-card parsing and serialization.

A card is a Markdown file with optional ``+++``-fenced TOML frontmatter::

    +++
    title = "..."
    aliases = [...]
    tags = [...]
    extends = []
    supersedes = []
    load = "always"     # optional; default "as-needed"
    +++

    One or two sentence summary paragraph.

    - Atomic statement with a [[wikilink]].

Parsing is lenient (so the index can always make progress on hand-edited
files); strictness lives in ``validate()``. Serialization keeps untouched parts
of a card byte-for-byte so human formatting and TOML comments survive edits
that don't concern them.

Plain Markdown needs no conversion: a file without frontmatter takes its title
from its first ``# heading`` (or its file name) and its summary from its first
prose paragraph. Legacy ``---`` YAML frontmatter (Jekyll, Hugo, Obsidian) is
read as a flat subset: scalars, ``[a, b]`` and ``- item`` lists, ``|``/``>``
blocks. Nested mappings are skipped with a warning. ``write()`` keeps a YAML
block verbatim unless it changes the card's fields, and then writes ``+++`` TOML.
"""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from dataclasses import dataclass, field
from typing import Any, Iterable

from . import tomlfmt
from .addressing import extract_wikilinks
from .lexical import normalize
from .errors import FrontmatterError

FENCE = "+++"
YAML_FENCE = "---"
KNOWN_FIELDS = ("title", "aliases", "tags", "extends", "supersedes", "load")
LIST_FIELDS = ("aliases", "tags", "extends", "supersedes")
# ``load = "always"``: the card is read into every session at start (persona, language, standing
# instructions), not only when a query hits it. ``"as-needed"`` (the default) is an ordinary card.
LOAD_ALWAYS = "always"
LOAD_AS_NEEDED = "as-needed"
LOAD_VALUES = (LOAD_ALWAYS, LOAD_AS_NEEDED)
SUMMARY_PREVIEW_CHARS = 240
MAX_CARD_LINES = 50
PARSER_VERSION = "2"  # in the index signature: "2" reads YAML frontmatter and plain-Markdown lead paragraphs

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
    frontmatter_format: str | None = None  # "toml" (+++), "yaml" (legacy ---) or None (plain Markdown)

    # -- typed accessors -------------------------------------------------
    @property
    def has_frontmatter(self) -> bool:
        return self.raw_frontmatter is not None

    @property
    def is_card_format(self) -> bool:
        """True for a native card (``+++`` TOML frontmatter); False for plain Markdown or YAML."""
        return self.frontmatter_format == "toml"

    def index_parts(self) -> tuple[str, str]:
        """``(summary, body)`` as indexed and previewed.

        A native card's summary is the paragraph right under its frontmatter. Plain Markdown and
        YAML-fronted notes usually open with a heading, so their summary is their first prose
        paragraph, taken out of the body so it is not counted twice.
        """
        if self.is_card_format or self.summary or self.errors:
            return self.summary, self.body
        return split_lead(self.body)

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

    @property
    def load(self) -> str:
        """``"always"`` or ``"as-needed"``; an invalid value counts as the default (validate() reports it)."""
        return LOAD_ALWAYS if self.frontmatter.get("load") == LOAD_ALWAYS else LOAD_AS_NEEDED

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
    fmt: str | None = None
    try:
        raw_fm, after = split_frontmatter(text)
    except FrontmatterError as exc:
        errors.append(str(exc))
        raw_fm, after = None, normalize_newlines(text)
    frontmatter: dict[str, Any] = {}
    if raw_fm is not None:
        fmt = "toml"
        try:
            frontmatter = tomllib.loads(raw_fm)
        except tomllib.TOMLDecodeError as exc:
            errors.append(f"invalid TOML frontmatter: {exc}")
            frontmatter = {}
        errors.extend(schema_errors(frontmatter))
        for name in LIST_FIELDS:
            if isinstance(frontmatter.get(name), str):
                warnings.append(f"frontmatter field {name!r} should be a list of strings")
    elif not errors:
        yaml = split_yaml_frontmatter(text)
        if yaml is not None:
            fmt = "yaml"
            raw_fm, after, frontmatter, yaml_warnings = yaml
            warnings.extend(yaml_warnings)
            errors.extend(schema_errors(frontmatter))
    summary, body = split_summary(after)
    return ParsedCard(frontmatter, raw_fm, after, summary, body, errors, warnings, fmt)


# ---------------------------------------------------------------------------
# Plain Markdown: lead paragraph and legacy YAML frontmatter
# ---------------------------------------------------------------------------


def split_lead(body: str) -> tuple[str, str]:
    """``(first prose paragraph, body without it)``; the paragraph is what ``first_paragraph`` finds."""
    lines = body.split("\n")
    in_fence = False
    start = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if start is not None:
            if not stripped or stripped.startswith(("```", "~~~")) or _BLOCK_START_RE.match(stripped):
                end = i
                break
            continue
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence or not stripped or _BLOCK_START_RE.match(stripped) or line.startswith(("    ", "\t")):
            continue
        start = i
    else:
        end = len(lines)
    if start is None:
        return "", body
    lead = " ".join(line.strip() for line in lines[start:end])
    rest = lines[:start] + lines[end:]
    while start < len(rest) and start > 0 and not rest[start].strip() and not rest[start - 1].strip():
        del rest[start]  # collapse the blank line pair the paragraph left behind
    return lead, "\n".join(rest).strip("\n")


_YAML_KEY_RE = re.compile(r"^([A-Za-z0-9_][\w-]*)[ \t]*:(?:[ \t]+(.*?))?[ \t]*$")
_YAML_BLOCK_SCALARS = ("|", ">", "|-", ">-", "|+", ">+")


def split_yaml_frontmatter(text: str) -> tuple[str, str, dict[str, Any], list[str]] | None:
    """``(raw, after, fields, warnings)`` for a leading ``---`` YAML block, or None when there is none.

    A block counts only if it is closed (``---`` or ``...``) and every line is a ``key: value``
    entry, a list item, an indented continuation or a comment; otherwise the ``---`` is a thematic
    break and the text is plain Markdown.
    """
    text = normalize_newlines(text)
    lines = text.split("\n")
    if not lines or lines[0].rstrip() != YAML_FENCE:
        return None
    close = next((i for i in range(1, len(lines)) if lines[i].rstrip() in (YAML_FENCE, "...")), None)
    if close is None:
        return None
    parsed = parse_yaml_subset(lines[1:close])
    if parsed is None:
        return None
    fields, warnings = parsed
    raw = "".join(line + "\n" for line in lines[1:close])
    return raw, "\n".join(lines[close + 1 :]), fields, warnings


def parse_yaml_subset(lines: list[str]) -> tuple[dict[str, Any], list[str]] | None:
    """Flat YAML: ``key: scalar``, flow and block lists of scalars, block scalars. Values stay strings."""
    fields: dict[str, Any] = {}
    warnings: list[str] = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()
        i += 1
        if not stripped or stripped.startswith("#"):
            continue
        m = _YAML_KEY_RE.match(line)
        if m is None:
            return None  # prose or an indented line at the top level: not a frontmatter block
        key, rest = m.group(1), _strip_yaml_comment(m.group(2) or "")
        value: Any
        if rest in _YAML_BLOCK_SCALARS:
            block: list[str] = []
            while i < n and (not lines[i].strip() or lines[i][:1] in (" ", "\t")):
                block.append(lines[i].strip())
                i += 1
            while block and not block[-1]:
                block.pop()
            value = "\n".join(block) if rest[0] == "|" else " ".join(b for b in block if b)
        elif rest.startswith("["):
            while rest.count("[") > rest.count("]") and i < n:
                rest += " " + lines[i].strip()
                i += 1
            items = _yaml_flow_list(rest)
            if items is None:
                warnings.append(f"YAML field {key!r} is not a flat list; ignored")
                continue
            value = items
        elif rest.startswith("{"):
            warnings.append(f"YAML field {key!r} is a mapping; ignored")
            continue
        elif rest == "":
            items, nested = [], False
            while i < n:
                s = lines[i].strip()
                if s and not s.startswith("#") and not (lines[i][:1] in (" ", "\t") or s == "-" or s.startswith("- ")):
                    break
                if s == "-" or s.startswith("- "):
                    items.append(_yaml_scalar(s[1:].strip()))
                elif s and not s.startswith("#"):
                    nested = True
                i += 1
            if nested:
                warnings.append(f"YAML field {key!r} is a nested mapping; ignored")
                continue
            if not items:
                continue  # null
            value = [v for v in items if v is not None]
        else:
            while i < n and lines[i].strip() and lines[i][:1] in (" ", "\t"):
                rest += " " + lines[i].strip()  # a folded multi-line scalar
                i += 1
            value = _yaml_scalar(rest)
            if value is None:
                continue
        if key in LIST_FIELDS and isinstance(value, str):
            value = [v.strip() for v in value.split(",") if v.strip()] if key == "tags" else [value]
        fields[key] = value
    return fields, warnings


def _strip_yaml_comment(value: str) -> str:
    if value[:1] in ("'", '"'):
        quote = value[0]
        end = value.find(quote, 1)
        while quote == "'" and end != -1 and value[end + 1 : end + 2] == "'":
            end = value.find(quote, end + 2)
        while quote == '"' and end != -1 and value[end - 1] == "\\":
            end = value.find(quote, end + 1)
        if end != -1:
            tail = value[end + 1 :]
            return value[: end + 1] if tail.strip().startswith("#") or not tail.strip() else value
        return value
    hash_at = value.find(" #")
    return value[:hash_at].rstrip() if hash_at != -1 else value


def _yaml_scalar(value: str) -> str | None:
    value = _strip_yaml_comment(value.strip())
    if len(value) >= 2 and value[0] == value[-1] == '"':
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value[1:-1]
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1].replace("''", "'")
    if value in ("", "~", "null", "Null", "NULL"):
        return None
    return value


def _yaml_flow_list(value: str) -> list[str] | None:
    value = _strip_yaml_comment(value.strip())
    if not (value.startswith("[") and value.endswith("]")):
        return None
    inner = value[1:-1]
    if "[" in inner or "{" in inner:
        return None
    items: list[str] = []
    current, quote = "", None
    for ch in inner + ",":
        if quote:
            current += ch
            if ch == quote:
                quote = None
        elif ch in ("'", '"') and not current.strip():
            quote = ch
            current += ch
        elif ch == ",":
            item = _yaml_scalar(current)
            if item is not None:
                items.append(item)
            current = ""
        else:
            current += ch
    return items


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
    if "load" in frontmatter and frontmatter["load"] not in LOAD_VALUES:
        errs.append(f"frontmatter field 'load' must be {' or '.join(repr(v) for v in LOAD_VALUES)} "
                    f"(got {frontmatter['load']!r})")
    return errs


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def ordered_frontmatter(fields: dict[str, Any]) -> dict[str, Any]:
    """Canonical key order: known fields first (always present), then extras in original order."""
    out: dict[str, Any] = {}
    out["title"] = fields.get("title") or ""
    if fields.get("load") is not None:  # written only when set, so ordinary cards keep their frontmatter
        out["load"] = fields["load"]
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
