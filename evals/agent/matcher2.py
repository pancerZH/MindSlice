"""Matcher v2: value matching that tolerates an agent's own wording (post-hoc; REPORT.md, "Re-score").

The frozen matcher (``judge.py``) asks whether MEME's annotation string occurs verbatim in a card. The audit
of tier 1 found that agents restate values in their own words far more often than they lose them, and that
two kinds of mention are not stale. v2 changes exactly those three things and nothing else:

1. **A value is stated when its content words are**, after light normalization: casefolded, number words and
   units unified ("ten" = "10", "minutes" = "min", "weekly" = "week", "twice" = "2x", "2 pm" = "2pm"),
   trailing plural "s" dropped, function words ignored. Order is free. A one- or two-word value must be on
   one line (as before); a longer one anywhere in the card; a bracketed type tag ("(book)", "(tv)",
   "(weekly)") is optional. A long value (12 content words or more, MEME's verbatim texts) is stated when
   90% of its words occur in order (line breaks and escapes ignored).
2. **A mention of an old value inside another entity's value is not that value**: "Synthari Modules" (a
   package manager) doesn't state the framework "Synthari". The haystack's other values that contain the
   old value are masked before it is looked for.
3. **What a line marks as past isn't presented as current**: after a prefix marker ("previously",
   "formerly", "switched from", "replaced", "supersedes", ...) or anywhere in a line with a suffix marker
   ("resolved", "no longer", "outdated", ...). Search-alias lines are keywords, not statements.

A card is stale for an old value when a statement line presents it (rules 1-3) and the card mentions no
current value (rule 1). A current value counts as kept (``lost``) only where it is presented as current.
MemoryAgentBench keeps its subject anchors: a value counts only on a line that also has them. Everything else
(warned, active, matchable, the metrics) is as in the frozen scorer.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Iterable, Sequence

from evals.external.datasets import normalize_text

_WORD = re.compile(r"\w+")
_STOP = frozenset("a an the of to in on at for and or with by is are was were be my our your their this that it as "
                  "from per via its".split())
_NUM = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8",
        "nine": "9", "ten": "10", "eleven": "11", "twelve": "12", "fifteen": "15", "twenty": "20", "thirty": "30",
        "forty": "40", "fifty": "50", "sixty": "60", "ninety": "90"}
_UNIT = {"mins": "min", "minute": "min", "minutes": "min", "hr": "hour", "hrs": "hour", "hours": "hour",
         "weeks": "week", "weekly": "week", "months": "month", "monthly": "month", "days": "day", "daily": "day",
         "years": "year", "yearly": "year", "annually": "year", "twice": "2x", "once": "1x", "thrice": "3x"}
_SYN = {"deleted": "delete", "deletion": "delete", "removed": "delete", "removal": "delete", "remove": "delete",
        "removing": "delete", "deleting": "delete"}
_TYPE_TAGS = frozenset("book tv anime film movie podcast show series week month day year".split())
# A prefix marker makes what follows it past ("Thyranote (switched from Xelvoria)": Xelvoria is past); a
# suffix marker makes the whole line past ("High blood pressure treated and resolved").
_PREFIX = re.compile(r"\b(?:previous|previously|formerly|former|(?<!\bis )(?<!\bare )(?<!\bbe )(?<!\bbeing )used to|"
                     r"switched (?:away )?from|switching from|changed from|moved (?:away )?from|transitioned from|"
                     r"updated from|replac(?:ed|es|ing)|instead of|supersed(?:es|ed|ing)|had been|was once)\b")
_SUFFIX = re.compile(r"\b(?:resolved|resolution|no longer|outdated|stopped|discontinued|cancell?ed)\b")
LONG = 12
COVERAGE = 0.90


def _norm_word(w: str) -> str:
    w = _SYN.get(w, w)
    w = _NUM.get(w, w)
    w = _UNIT.get(w, w)
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        w = w[:-1]
    return _UNIT.get(w, w)


def _prep(text: str) -> str:
    s = normalize_text(text).replace("\\n", " ")
    return re.sub(r"(\d)\s+(am|pm)\b", r"\1\2", s)


@lru_cache(maxsize=200_000)
def tokens(text: str) -> tuple[str, ...]:
    return tuple(_norm_word(w) for w in _WORD.findall(_prep(text)))


def phrase(value: str) -> str | None:
    """A value that is mostly function words ("in a relationship") must be matched as the phrase itself."""
    words = tokens(value)
    content = [t for t in words if t not in _STOP]
    return " ".join(words) if len(words) >= 2 and len(content) <= 1 else None


def _has_phrase(text: str, ph: str) -> bool:
    return re.search(r"(?<!\w)" + re.escape(ph) + r"(?!\w)", " ".join(tokens(text))) is not None


@lru_cache(maxsize=50_000)
def value_parts(value: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(required content words, all content words) of a value; a bracketed type tag is optional."""
    allw = tuple(t for t in tokens(value) if t not in _STOP)
    m = re.fullmatch(r"(.*?)\s*\(([^()]*)\)\s*", value)
    if m:
        inside = [t for t in tokens(m.group(2)) if t not in _STOP]
        outside = tuple(t for t in tokens(m.group(1)) if t not in _STOP)
        if outside and len(inside) == 1 and inside[0] in _TYPE_TAGS:
            return outside, allw
    return allw, allw


def _in_order(needle: Sequence[str], hay: Sequence[str]) -> float:
    """Share of ``needle`` matched in order within ``hay`` (greedy)."""
    if not needle:
        return 0.0
    from difflib import SequenceMatcher

    m = SequenceMatcher(None, list(needle), list(hay), autojunk=False)
    return sum(b.size for b in m.get_matching_blocks()) / len(needle)


def current_region(line: str) -> str:
    """The part of a normalized line that isn't marked as past."""
    if _SUFFIX.search(line):
        return ""
    m = _PREFIX.search(line)
    return line[: m.start()] if m else line


class Text:
    """A card's text, split for matching. Alias lines are search keywords, not statements."""

    def __init__(self, raw: str = "", title: str | None = None, aliases: Sequence[str] = (), summary: str = "",
                 body: str = "") -> None:
        if title is not None:
            parts = [(title, False)] + [(a, True) for a in aliases] + [(l, False) for l in (summary + "\n" + body).split("\n")]
        else:
            parts = [(l, False) for l in raw.split("\n")]
        parts = [(l, a) for l, a in parts if l.strip()]
        self.lines = [l for l, _ in parts]
        self.is_alias = [a for _, a in parts]
        self.norm_lines = [_prep(l) for l in self.lines]
        self.line_tokens = [frozenset(tokens(l)) for l in self.lines]
        self.all_tokens = tokens("\n".join(self.lines))
        self.token_set = frozenset(self.all_tokens)
        self.regions = [current_region(n) for n in self.norm_lines]
        self.region_tokens = [frozenset(tokens(r)) for r in self.regions]
        self.region_set = frozenset().union(*self.region_tokens) if self.region_tokens else frozenset()


def _anchor_ok(toks: frozenset, anchors) -> bool:
    return not anchors or {_norm_word(w) for w in anchors} <= toks


def states(t: Text, value: str, anchors=None) -> bool:
    """The card mentions the value (any line, any tense). MemoryAgentBench: on a line with its subject anchors."""
    ph = phrase(value)
    if ph:
        return any(_has_phrase(l, ph) and _anchor_ok(lt, anchors) for l, lt in zip(t.lines, t.line_tokens))
    req, allw = value_parts(value)
    if not req:
        return value in " ".join(t.norm_lines)
    if len(allw) >= LONG and not anchors:
        return _in_order(allw, t.all_tokens) >= COVERAGE
    need = set(req)
    if len(need) <= 2 or anchors:
        return any(need <= lt and _anchor_ok(lt, anchors) for lt in t.line_tokens)
    return need <= t.token_set


def states_any(t: Text, values: Iterable[str], anchors=None) -> bool:
    return any(states(t, v, anchors) for v in values)


def states_current(t: Text, value: str, anchors=None) -> bool:
    """The card states the value as current: in a part of a line not marked as past (``lost``)."""
    ph = phrase(value)
    if ph:
        return any(_has_phrase(r, ph) and _anchor_ok(lt, anchors) for r, lt in zip(t.regions, t.line_tokens))
    req, allw = value_parts(value)
    if not req:
        return any(value in r for r in t.regions)
    if len(allw) >= LONG and not anchors:
        return _in_order(allw, t.all_tokens) >= COVERAGE
    need = set(req)
    if len(need) <= 2 or anchors:
        return any(need <= rt and _anchor_ok(lt, anchors) for rt, lt in zip(t.region_tokens, t.line_tokens))
    return need <= t.region_set


def _masks(value: str, others: Sequence[str]) -> list[re.Pattern]:
    """Phrases of other values that contain ``value``: the value plus its neighbouring word in them."""
    out = []
    v = _prep(value)
    for w in others:
        w = _prep(w)
        if w == v or v not in w:
            continue
        i = w.find(v)
        after = w[i + len(v):].split()
        before = w[:i].split()
        if after:
            out.append(re.compile(re.escape(v) + r"\W+" + re.escape(after[0].strip(".,;:()"))))
        if before:
            out.append(re.compile(re.escape(before[-1].strip(".,;:()")) + r"\W+" + re.escape(v)))
    return out


def presents_old(t: Text, value: str, others: Sequence[str] = (), anchors=None) -> bool:
    """A statement line presents ``value`` as current: not an alias, not inside another entity's value, not in
    a part marked as past."""
    ph = phrase(value)
    req, allw = value_parts(value)
    if not req and not ph:
        return False
    masks = _masks(value, others)
    need = set(req)
    for alias, region, lt in zip(t.is_alias, t.regions, t.line_tokens):
        if alias or not region:
            continue
        line = region
        for m in masks:
            line = m.sub(" ", line)
        rt = tokens(line)
        if ph:
            if _has_phrase(line, ph) and _anchor_ok(lt, anchors):
                return True
        elif len(allw) >= LONG and not anchors:
            if _in_order(allw, rt) >= COVERAGE:
                return True
        elif need <= frozenset(rt) and _anchor_ok(lt, anchors):
            return True
    return False


def is_stale(t: Text, stale: Sequence[str], current: Sequence[str], others: Sequence[str] = (), anchors=None) -> bool:
    if states_any(t, current, anchors):
        return False
    return any(presents_old(t, s, others, anchors) for s in stale)
