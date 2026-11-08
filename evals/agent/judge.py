"""Value-based judgments on any workspace (agent_test.md 6.1).

Agent cards correspond to no dataset turn, so a card is judged by what it *states*:

* A card **states** a value when the normalized value (``evals.external.datasets.normalize_value``) is a
  substring of the card's normalized text (title, aliases, summary and body) that doesn't continue a
  longer word: "paris" is not stated by "Le Petit Parisien", nor "india" by "Indiana".
* MemoryAgentBench's objects are generic words ("basketball", "London") that hundreds of unrelated facts
  share, so there a value is stated only by a **line** of the card (the title, an alias, a summary or body
  line) that also holds every subject anchor word of the judged fact (``subject_anchors``). On a flat fact
  card (one fact) this is the same as the plain rule. This scoping was fixed before any LLM run, on the
  flat and oracle workspaces only (PLAN.md).
* A card is **stale** for a question when it states a stale value and no current value.
* A card is **warned** exactly as in Mode B (``evals/external/harness.py``): status not ``active``, or
  ``baseline_superseded_by`` / ``missing_baselines`` (over the whole extends closure).

``Judge`` reads card files and the lineage index directly (``mindslice.query._Ctx``), never through
``read()``, so judging changes nothing in the workspace (no read telemetry).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Iterable, Sequence

from evals.external.datasets import normalize_text, words
from mindslice import Workspace
from mindslice.card import parse_card
from mindslice.writer import read_card_file
from mindslice.query import _Ctx, _baseline_closure

K = 10


@dataclass(frozen=True)
class CardText:
    norm: str  # whole card, normalized
    lines: tuple[tuple[str, frozenset[str]], ...]  # each line normalized, with its words


def card_text(title: str, aliases: Sequence[str], summary: str, body: str) -> CardText:
    raw_lines = [title, *aliases, *summary.split("\n"), *body.split("\n")]
    lines = []
    for line in raw_lines:
        n = normalize_text(line)
        if n:
            lines.append((n, frozenset(words(n))))
    return CardText(normalize_text("\n".join(raw_lines)), tuple(lines))


MATCH_MODE = "word"  # "word": the value may not continue a longer word; "substring": the spec's literal rule


@lru_cache(maxsize=65536)
def _pattern(value: str) -> re.Pattern[str]:
    head = r"(?<!\w)" if value[:1].isalnum() or value[:1] == "_" else ""
    tail = r"(?!\w)" if value[-1:].isalnum() or value[-1:] == "_" else ""
    return re.compile(head + re.escape(value) + tail)


def contains(haystack: str, value: str) -> bool:
    """``value`` occurs in ``haystack``, not glued to letters or digits ("paris" is not in "parisien")."""
    if value not in haystack:
        return False
    return MATCH_MODE == "substring" or _pattern(value).search(haystack) is not None


def states(text: CardText, value: str, anchors: Sequence[str] | None = None) -> bool:
    if not value:
        return False
    if not anchors:
        return contains(text.norm, value)
    need = set(anchors)
    return any(need <= toks and contains(line, value) for line, toks in text.lines)


def states_any(text: CardText, values: Iterable[str], anchors: Sequence[str] | None = None) -> bool:
    return any(states(text, v, anchors) for v in values)


def is_stale(text: CardText, stale: Sequence[str], current: Sequence[str], anchors: Sequence[str] | None = None) -> bool:
    return states_any(text, stale, anchors) and not states_any(text, current, anchors)


class Judge:
    """Snapshots of one workspace: card texts (cached by file mtime and size) and lineage flags."""

    def __init__(self, ws: Workspace) -> None:
        self.ws = ws
        self._texts: dict[str, tuple[tuple[int, int], CardText]] = {}
        self._rows: dict[str, Any] = {}

    # -- snapshot ----------------------------------------------------------
    def refresh(self) -> None:
        """Sync the index with the files (any public call does) and reload the card list."""
        self.ws.manifest(limit=1)
        table = self.ws.table()
        rows = {}
        for row in self.ws.index.all_cards():
            if row["is_overview"]:
                continue
            rows[f"{row['mount']}/{row['path']}"] = row
        self._rows = rows
        self._roots = {m.alias: m.root for m in table.all()}

    def addresses(self) -> list[str]:
        return list(self._rows)

    def text(self, address: str) -> CardText | None:
        row = self._rows.get(address)
        if row is None:
            return None
        key = (row["mtime_ns"], row["size"])
        hit = self._texts.get(address)
        if hit is not None and hit[0] == key:
            return hit[1]
        raw, _ = read_card_file(self._roots[row["mount"]] / f"{row['path']}.md")
        if raw is None:
            return None
        parsed = parse_card(raw)
        text = card_text(parsed.display_title(row["path"]), parsed.aliases, parsed.summary, parsed.body)
        self._texts[address] = (key, text)
        return text

    def flags(self, addresses: Iterable[str]) -> dict[str, tuple[bool, bool]]:
        """address -> (active, warned), as a search preview would report them."""
        out = {}
        with self.ws._reading() as table:
            ctx = _Ctx(self.ws, table, True)
            for a in addresses:
                status = ctx.status(a)["status"]
                baselines, missing = _baseline_closure(ctx, a)
                replaced = any(ctx.lv.all_superseders(b) for b in baselines)
                active = status == "active"
                out[a] = (active, (not active) or replaced or bool(missing))
        return out

    # -- whole-workspace judgments -------------------------------------------
    def stating(self, values: Sequence[str], anchors: Sequence[str] | None = None,
                unless: Sequence[str] = ()) -> list[str]:
        """Every card that states one of ``values`` (and none of ``unless``)."""
        return [a for a in self._rows if (t := self.text(a)) is not None and states_any(t, values, anchors)
                and not states_any(t, unless, anchors)]

    def active_stale(self, stale: Sequence[str], current: Sequence[str], anchors: Sequence[str] | None = None) -> list[str]:
        """Active, unwarned cards that state a stale value and no current one (``retired`` fails on these)."""
        cands = self.stating(stale, anchors, unless=current)
        return [a for a, (active, warned) in self.flags(cands).items() if active and not warned]

    def active_stating(self, values: Sequence[str], anchors: Sequence[str] | None = None) -> list[str]:
        """Active cards (warned or not) that state one of ``values`` (``lost`` and ``forgotten``)."""
        cands = self.stating(values, anchors)
        return [a for a, (active, _) in self.flags(cands).items() if active]

    # -- the first page -------------------------------------------------------
    def page(self, query: str, k: int = K) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        res = self.ws.search(query, k=k)
        out = []
        for r in res["results"]:
            warned = r["status"] != "active" or bool(r.get("baseline_superseded_by") or r.get("missing_baselines"))
            out.append({"address": r["address"], "warned": warned, "via": list(r.get("matched_via_superseded", []))})
        return out, res
