"""Turning benchmark dialogue into MindSlice cards, and cards into workspaces.

One rule set for every dataset (PLAN.md, "Compilation"), fixed before any search was scored:

* **Path:** opaque and chronological: ``s007`` (a session), ``s007/r002`` (a round), ``s007/t013`` (a turn),
  ``f00042`` (a numbered fact). Dataset ids never reach a card: LongMemEval names its evidence sessions
  ``answer_…`` and MEME ``evidence_…``, and the card path is indexed.
* **Title:** the card's speakers, in order of appearance, joined by "and" ("User and assistant", "Caroline").
* **Tags:** the same speakers.
* **Summary:** the card's first line of dialogue (the first user line when the dataset has a user role),
  cut to 240 characters.
* **Body:** ``- Date: …`` (when the dataset gives one), then one bullet per turn, ``- Speaker: text``, in
  full. Image captions follow their turn as ``- Speaker shared an image: caption``.
* **Lineage:** none in Mode A. Mode B adds ``supersedes`` / ``extends`` through ``Workspace.write``.

A round is a user turn plus the assistant turns that follow it; turns before the first user turn join
the first round. Text keeps its line breaks (as continuation lines of its bullet); ``[[`` is written
``[ [`` so dialogue can never create a wikilink.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from mindslice import Workspace
from mindslice.card import SUMMARY_PREVIEW_CHARS, truncate
from mindslice.writer import build_text

USER_ROLES = ("user",)


@dataclass(frozen=True)
class Turn:
    speaker: str  # as shown in the card ("User", "Assistant", "Caroline")
    text: str
    ref: str  # dataset-level id of the turn, for judgments (never written to the card)
    role: str = ""  # "user" / "assistant" when the dataset has roles
    extra: tuple[str, ...] = ()  # e.g. an image caption


@dataclass(frozen=True)
class Session:
    ref: str
    date: str
    turns: tuple[Turn, ...]


@dataclass
class Card:
    path: str
    title: str
    tags: list[str]
    summary: str
    body: list[str]
    units: tuple[str, ...]  # turn refs this card holds
    session: str  # session ref
    extends: list[str] = field(default_factory=list)
    supersedes: list[str] = field(default_factory=list)

    def render(self) -> str:
        """Exactly the file ``Workspace.write(self.path, op="create", ...)`` writes (same engine function)."""
        text, _ = build_text("create", self.path, None, **self.write_args())
        assert text is not None
        return text

    def write_args(self) -> dict:
        return {"content": self.body, "summary": self.summary, "title": self.title, "tags": self.tags,
                "aliases": None, "extends": self.extends or None, "supersedes": self.supersedes or None}


# ---------------------------------------------------------------------------
# Text rules
# ---------------------------------------------------------------------------

_LEADING_MARKUP = re.compile(r"^(?:[-*+>#|<`~=_]+|\d+[.)])\s*")


def clean(text: str) -> str:
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").replace("[[", "[ [").strip()


def summary_line(text: str) -> str:
    """One line, no leading Markdown markup (it would turn the summary paragraph into a list or block)."""
    line = " ".join(clean(text).split())
    while True:
        stripped = _LEADING_MARKUP.sub("", line, count=1)
        if stripped == line:
            break
        line = stripped
    return truncate(line, SUMMARY_PREVIEW_CHARS)[0]


def bullet(label: str, text: str) -> str:
    """``label: text`` as one statement; later lines are indented so they stay inside the bullet."""
    lines = [l.strip() for l in clean(text).split("\n") if l.strip()]
    if not lines:
        return f"{label}:"
    head, *rest = lines
    return "\n".join([f"{label}: {head}", *(f"  {l}" for l in rest)])


def make_card(path: str, turns: Sequence[Turn], date: str, session: str) -> Card:
    speakers = list(dict.fromkeys(t.speaker for t in turns))
    first = next((t for t in turns if t.role in USER_ROLES), turns[0])
    body = [f"Date: {date}"] if date else []
    for t in turns:
        body.append(bullet(t.speaker, t.text))
        body += [bullet(f"{t.speaker} shared an image", x) for x in t.extra]
    title = " and ".join(speakers)
    title = title[:1].upper() + title[1:]
    return Card(path, title, speakers, summary_line(first.text), body, tuple(t.ref for t in turns), session)


def rounds(turns: Sequence[Turn]) -> list[list[Turn]]:
    out: list[list[Turn]] = []
    for t in turns:
        if t.role in USER_ROLES and out and any(x.role in USER_ROLES for x in out[-1]):
            out.append([t])
        elif not out:
            out.append([t])
        else:
            out[-1].append(t)
    return out


def _width(n: int) -> int:
    """Zero padding so that address order (the engine's last tie-break) is chronological order."""
    return max(3, len(str(max(n - 1, 0))))


def session_cards(sessions: Sequence[Session]) -> list[Card]:
    w = _width(len(sessions))
    return [make_card(f"s{i:0{w}d}", s.turns, s.date, s.ref) for i, s in enumerate(sessions) if s.turns]


def round_cards(sessions: Sequence[Session]) -> list[Card]:
    w = _width(len(sessions))
    out = []
    for i, s in enumerate(sessions):
        rs = rounds(s.turns)
        out += [make_card(f"s{i:0{w}d}/r{j:0{_width(len(rs))}d}", r, s.date, s.ref) for j, r in enumerate(rs)]
    return out


def turn_cards(sessions: Sequence[Session]) -> list[Card]:
    w = _width(len(sessions))
    return [make_card(f"s{i:0{w}d}/t{j:0{_width(len(s.turns))}d}", [t], s.date, s.ref)
            for i, s in enumerate(sessions) for j, t in enumerate(s.turns)]


GRANULARITY = {"session": session_cards, "round": round_cards, "turn": turn_cards}


# ---------------------------------------------------------------------------
# Workspaces
# ---------------------------------------------------------------------------


def new_workspace(root: Path) -> Workspace:
    return Workspace.init(root)


def add_files(ws: Workspace, cards: Iterable[Card]) -> None:
    """Bulk ingestion: write each card's file into the overlay, then let one public call index them all.

    Byte-identical to ``Workspace.write(op="create")`` card by card (``Card.render`` uses the engine's own
    ``build_text``; ``tests/test_external_eval.py`` checks it), without a sync per card.
    """
    overlay = ws.table().overlay.root
    for card in cards:
        target = overlay / f"{card.path}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(card.render(), encoding="utf-8")
        os.replace(tmp, target)
    ws.manifest(limit=1)  # any public call syncs the index with the files just written


def write_card(ws: Workspace, card: Card) -> dict:
    """One card through the public write path (Mode B), with its lineage."""
    return ws.write(card.path, op="create", **card.write_args())


def address(card_or_path: Card | str) -> str:
    path = card_or_path.path if isinstance(card_or_path, Card) else card_or_path
    return f"@overlay/{path}"
