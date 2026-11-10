"""Matcher v3: matcher v2 with the error classes its audits found fixed (post-hoc; REPORT.md, "Matcher v3").

v2 (``matcher2.py``) stays frozen: the confirmatory run was pre-registered with it. v3 keeps every v2 rule
and changes only these:

1. **Times**: "2:00 PM", "2 p.m." and "2pm" are one form; "11:00 PM to 5:30 AM" states "11pm-5:30am".
2. **Modal verbs are function words** (not "may", a month): "allows any team member to approve" states
   "any team member can approve".
3. **"-ies" and "-ly"**: "stories" is "story", "continuously" is "continuous" (with v2's plural "s").
   No -ed, -ing or final -e: MEME's relationship statuses collide with ordinary words ("engaged" and an
   "engaging" book, "separated" and "separate" rooms), so "required" and "requires" stay apart.
4. **Long values** (12 content words or more): the share of the value's words found in order in the card is
   the longest common subsequence, not v2's greedy alignment (which an abridged quote earlier in the card
   could anchor wrongly: 0.61 for a card quoting the text word for word). Statement lines are joined, so a
   log split into bullets still counts.
5. **More past markers**, the ones found on the audited cards. Before the value, as in v2 (the rest of
   the line is past): "prior", "invalidates", "shifted from", "changes the build tool from" (a verb, up to three
   words, then "from"). Anywhere in a sentence, making that
   sentence past (not the whole line, as v2's "resolved" does: "everyone's paths have changed" in a user's
   turn doesn't retire the reunion in the sentence before): "invalidated", "is subject to change", "has
   changed", "affected by", "depended on", "superseded by", "was removed".

Everything else (warned, active, matchable, anchors, masks, the metrics) is as in v2.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Iterable, Sequence

from evals.external.datasets import normalize_text

_WORD = re.compile(r"\w+")
_STOP = frozenset("a an the of to in on at for and or with by is are was were be my our your their this that it as "
                  "from per via its can could will would should might must".split())  # not "may": a month
_NUM = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8",
        "nine": "9", "ten": "10", "eleven": "11", "twelve": "12", "fifteen": "15", "twenty": "20", "thirty": "30",
        "forty": "40", "fifty": "50", "sixty": "60", "ninety": "90"}
_UNIT = {"mins": "min", "minute": "min", "minutes": "min", "hr": "hour", "hrs": "hour", "hours": "hour",
         "weeks": "week", "weekly": "week", "months": "month", "monthly": "month", "days": "day", "daily": "day",
         "years": "year", "yearly": "year", "annually": "year", "twice": "2x", "once": "1x", "thrice": "3x"}
_SYN = {"deleted": "delete", "deletion": "delete", "removed": "delete", "removal": "delete", "remove": "delete",
        "removing": "delete", "deleting": "delete"}
# A prefix marker makes what follows it past ("Thyranote (switched from Xelvoria)": Xelvoria is past); a
# suffix marker makes the whole line past ("High blood pressure treated and resolved").
_VERB_FROM = (r"(?:switch(?:ed|es|ing)?|chang(?:e|es|ed|ing)|mov(?:e|es|ed|ing)|transition(?:ed|s|ing)?|"
              r"updat(?:e|es|ed|ing)|shift(?:s|ed|ing)?|migrat(?:e|es|ed|ing))(?:\W+(?!to\b)\w+){0,3}?\W+(?:away\W+)?from")
_PREFIX = re.compile(r"\b(?:" + _VERB_FROM + r"|previous|previously|prior|formerly|former|originally|"
                     r"(?<!\bis )(?<!\bare )(?<!\bbe )(?<!\bbeing )used to|"
                     r"replac(?:ed|es|ing)|instead of|supersed(?:es|ed|ing)|had been|was once|invalidat(?:es|ing))\b")
_SUFFIX = re.compile(r"\b(?:resolved|resolution|no longer|outdated|stopped|discontinued|cancell?ed)\b")  # v2: the line
_SUFFIX3 = re.compile(r"\b(?:invalidated|subject to change|(?:has|have|had) (?:since |now |already )?changed|affected by|"
                      r"(?:is|are|was|were|be|been) (?:(?!not\b)\w+ )?affected|depended on|"
                      r"(?:was|were) (?:explicitly |directly )?(?:dependent on|determined by)|superseded by|"
                      r"(?:was|were|been|is|are) (?:\w+ )?(?:removed|deleted|dropped))\b")  # v3: the sentence
_SENT = re.compile(r"(?<=[.;!?])\s+")
LONG = 12
COVERAGE = 0.90
_TIME00 = re.compile(r"\b(\d{1,2}):00\s*(am|pm)\b")
_AMPM = re.compile(r"(\d)\s*([ap])\.\s?m\.?(?!\w)")


def _stem(w: str) -> str:
    """A plural "s" off (as v2), "-ies" -> "y", and "-ly" off when five letters stay ("continuously" ->
    "continuous"). No -ed, -ing or final -e: MEME's statuses would collide ("engaged" and "engaging",
    "separated" and "separate")."""
    if not w.isalpha():
        return w
    if w.endswith("ies") and len(w) >= 6:
        return w[:-3] + "y"
    if w.endswith("ly") and len(w) - 2 >= 5:
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
        return w[:-1]
    return w


def _norm_word(w: str) -> str:
    w = _SYN.get(w, w)
    w = _NUM.get(w, w)
    w = _UNIT.get(w, w)
    w = _stem(w)
    return _UNIT.get(w, w)


_TYPE_TAGS = frozenset(_norm_word(w) for w in "book tv anime film movie podcast show series week month day year".split())


def _prep(text: str) -> str:
    s = normalize_text(text).replace("\\n", " ")
    s = _AMPM.sub(r"\1\2m", s)
    s = _TIME00.sub(r"\1\2", s)
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


def lcs(a: Sequence[str], b: Sequence[str]) -> int:
    """Length of the longest common subsequence (bit-parallel; bits over ``a``)."""
    if not a or not b:
        return 0
    masks: dict[str, int] = {}
    for i, x in enumerate(a):
        masks[x] = masks.get(x, 0) | (1 << i)
    full = (1 << len(a)) - 1
    v = full
    for y in b:
        u = v & masks.get(y, 0)
        v = ((v + u) | (v - u)) & full
    return len(a) - bin(v).count("1")


def _covered(needle: Sequence[str], hay: Sequence[str], hay_set: frozenset | set | None = None) -> bool:
    if not needle:
        return False
    hs = hay_set if hay_set is not None else set(hay)
    if sum(1 for t in needle if t in hs) < COVERAGE * len(needle):  # cheap bound first
        return False
    return lcs(needle, hay) >= COVERAGE * len(needle)


def current_region(line: str) -> str:
    """The part of a normalized line that isn't marked as past: before a prefix marker (the rest of the line
    is past, as in v2), without the sentences a v3 suffix marker is in, and nothing if a v2 suffix marker is
    anywhere in it."""
    if _SUFFIX.search(line):
        return ""
    if _SUFFIX3.search(line):
        line = " ".join(x for x in _SENT.split(line) if not _SUFFIX3.search(x))
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
        return _covered(allw, t.all_tokens, t.token_set)
    need = set(req)
    if len(need) <= 2 or anchors:
        return any(need <= lt and _anchor_ok(lt, anchors) for lt in t.line_tokens)
    return need <= t.token_set


def states_any(t: Text, values: Iterable[str], anchors=None) -> bool:
    return any(states(t, v, anchors) for v in values)


def states_current(t: Text, value: str, anchors=None) -> bool:
    """The card states the value as current: in a part of a line not marked as past (``lost``). A long value
    (a verbatim text) counts anywhere in the card, as in v2: logs carry words like "stopped"."""
    ph = phrase(value)
    if ph:
        return any(_has_phrase(r, ph) and _anchor_ok(lt, anchors) for r, lt in zip(t.regions, t.line_tokens))
    req, allw = value_parts(value)
    if not req:
        return any(value in r for r in t.regions)
    if len(allw) >= LONG and not anchors:
        return _covered(allw, t.all_tokens, t.token_set)
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
    a part marked as past. A long value: its words in order across the card's statement lines."""
    ph = phrase(value)
    req, allw = value_parts(value)
    if not req and not ph:
        return False
    masks = _masks(value, others)
    need = set(req)
    joined: list[str] = []
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
            joined += rt
        elif need <= frozenset(rt) and _anchor_ok(lt, anchors):
            return True
    return bool(joined) and _covered(allw, joined)


def is_stale(t: Text, stale: Sequence[str], current: Sequence[str], others: Sequence[str] = (), anchors=None) -> bool:
    if states_any(t, current, anchors):
        return False
    return any(presents_old(t, s, others, anchors) for s in stale)
