"""Language-aware lexical analysis for the FTS5 index (standard library only).

SQLite's ``unicode61`` tokenizer splits text on spaces and punctuation. Chinese,
Japanese, Thai, Khmer, Myanmar and Tibetan do not put spaces between words (and Korean
attaches particles to words), so a whole run would become one token and any partial
query would silently miss. MindSlice therefore analyzes these scripts itself, *before*
text reaches FTS5:

* **Normalization** (index and query): NFKC folds full-width ASCII (``ＪＷＴ`` -> ``JWT``)
  and half-width kana (``ﾄｰｸﾝ`` -> ``トークン``); variation selectors and zero-width
  characters are dropped so visually identical text matches.
* **Units**: a run of an unspaced script is split into grapheme-like units - a letter or
  number plus any combining marks after it (Thai vowels/tones, Khmer coeng, Tibetan stacks).
  Punctuation and symbols (``，``, ``・``, Tibetan tsheg ``་``) separate runs.
* **Indexing**: every run is rewritten as its unigrams followed by its overlapping bigrams
  (``令牌过期`` -> ``令 牌 过 期 令牌 牌过 过期``). Unigrams make single-character queries work
  anywhere inside a run; keeping the bigrams contiguous keeps verbatim matching possible.
  Latin and other spaced scripts are left to ``porter unicode61`` (stemming, case folding).
* **Querying**: each run in a query becomes its bigrams, OR-ed like ordinary words (a
  one-unit run becomes its unigram). Partial overlap is *found and ranked lower* instead of
  silently missed; the run's contiguous bigram phrase is a reported signal (``Index.search``).
* **Vocabulary**: the spaced-script words of each card (``surface_words``) are kept unstemmed,
  so ``search()`` can say which query words no card contains and suggest close words that
  do occur (``did_you_mean``). Unspaced runs get no suggestions.

The analysis depends on Python's bundled Unicode database (``unicodedata.unidata_version``);
``ANALYZER_VERSION`` plus that version are recorded in the index so a change re-indexes.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

ANALYZER_VERSION = "2"  # 2: the surface vocabulary (card_words) is derived at index time

# Unicode blocks of scripts written without spaces between words. Blocks are listed whole;
# each code point's general category decides its role: letters/numbers start a unit,
# combining marks attach to the previous unit, everything else (punctuation, symbols,
# unassigned) separates runs. Huge ideograph blocks are taken wholesale (all letters).
SCRIPT_BLOCKS: tuple[tuple[int, int], ...] = (
    # --- CJK -------------------------------------------------------------------------
    (0x1100, 0x11FF),  # Hangul Jamo
    (0x3000, 0x303F),  # CJK symbols & punctuation (keeps 々 〆 〇 and Hangzhou numerals)
    (0x3040, 0x309F),  # Hiragana
    (0x30A0, 0x30FF),  # Katakana
    (0x3100, 0x312F),  # Bopomofo
    (0x3130, 0x318F),  # Hangul compatibility Jamo
    (0x31A0, 0x31BF),  # Bopomofo extended
    (0x31F0, 0x31FF),  # Katakana phonetic extensions
    (0x3400, 0x4DBF),  # CJK unified ideographs extension A
    (0x4E00, 0x9FFF),  # CJK unified ideographs
    (0xA960, 0xA97F),  # Hangul Jamo extended-A
    (0xAC00, 0xD7AF),  # Hangul syllables
    (0xD7B0, 0xD7FF),  # Hangul Jamo extended-B
    (0xF900, 0xFAFF),  # CJK compatibility ideographs
    (0xFF66, 0xFFDC),  # half-width Katakana / Hangul (NFKC folds these; kept for robustness)
    (0x1AFF0, 0x1AFFF),  # Kana extended-B
    (0x1B000, 0x1B16F),  # Kana supplement, extended-A, small kana extension
    (0x20000, 0x2FA1F),  # CJK extensions B-F, I and compatibility supplement
    (0x30000, 0x323AF),  # CJK extensions G-H
    # --- Southeast Asian & Tibetan --------------------------------------------------
    (0x0E00, 0x0E7F),  # Thai
    (0x0F00, 0x0FFF),  # Tibetan
    (0x1000, 0x109F),  # Myanmar
    (0x1780, 0x17FF),  # Khmer
    (0xA9E0, 0xA9FF),  # Myanmar extended-B
    (0xAA60, 0xAA7F),  # Myanmar extended-A
)
# Combining marks from outside the blocks that still attach inside a run (e.g. an accent).
_GENERIC_MARKS: tuple[tuple[int, int], ...] = (
    (0x0300, 0x036F), (0x1AB0, 0x1AFF), (0x1DC0, 0x1DFF), (0x20D0, 0x20FF), (0xFE20, 0xFE2F),
)
_WHOLESALE = 6000  # blocks at least this large are ideographs/syllables: no per-point check


def _merge(points: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for lo, hi in sorted(points):
        if merged and lo <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(hi, merged[-1][1]))
        else:
            merged.append((lo, hi))
    return merged


def _char_class(ranges: list[tuple[int, int]]) -> str:
    return "".join(f"\\U{lo:08x}" if lo == hi else f"\\U{lo:08x}-\\U{hi:08x}" for lo, hi in ranges)


def _build_classes() -> tuple[str, str]:
    base: list[tuple[int, int]] = []
    marks: list[tuple[int, int]] = list(_GENERIC_MARKS)
    for lo, hi in SCRIPT_BLOCKS:
        if hi - lo + 1 >= _WHOLESALE:
            base.append((lo, hi))
            continue
        for cp in range(lo, hi + 1):
            kind = unicodedata.category(chr(cp))[0]
            if kind in "LN":
                base.append((cp, cp))
            elif kind == "M":
                marks.append((cp, cp))
    return _char_class(_merge(base)), _char_class(_merge(marks))


_BASE_CLASS, _MARK_CLASS = _build_classes()
_BASE = re.compile(f"[{_BASE_CLASS}]")
_RUN = re.compile(f"[{_BASE_CLASS}][{_BASE_CLASS}{_MARK_CLASS}]*")
# Default-ignorable characters that must not change what text matches.
_IGNORABLE = re.compile("[­​-‍⁠﻿︀-️\U000e0100-\U000e01ef]")
_WORD = re.compile(r"\w+(\*)?")
_TOKEN = re.compile(r"[^\W_]+")  # what unicode61 keeps as a token (letters and digits; "_" separates)
SUGGEST_MIN_CHARS = 3  # shorter words get no suggestions, and are not kept in the vocabulary


def normalize(text: str) -> str:
    """Search-side normalization: drop ignorable characters, then NFKC."""
    return unicodedata.normalize("NFKC", _IGNORABLE.sub("", text or ""))


def fold(text: str) -> str:
    """Normalization for exact-match keys (aliases, tags): NFKC + case folding + whitespace."""
    return " ".join(normalize(text).casefold().split())


def _units(run: str) -> list[str]:
    """Split a run into grapheme-like units (a base character plus attached marks)."""
    units: list[str] = []
    for ch in run:
        if units and not _BASE.match(ch):
            units[-1] += ch
        else:
            units.append(ch)
    return units


def _bigrams(units: list[str]) -> list[str]:
    return [a + b for a, b in zip(units, units[1:])]


def index_text(text: str) -> str:
    """Rewrite text for indexing: unspaced-script runs become ``unigrams... bigrams...``."""
    text = normalize(text)
    if not _BASE.search(text):
        return text
    out: list[str] = []
    last = 0
    for m in _RUN.finditer(text):
        out.append(text[last : m.start()])
        units = _units(m.group())
        tokens = units if len(units) == 1 else units + _bigrams(units)
        out.append(" " + " ".join(tokens) + " ")
        last = m.end()
    out.append(text[last:])
    return "".join(out)


def surface_words(text: str) -> set[str]:
    """Spaced-script words of ``text``, NFKC + case-folded and unstemmed (the vocabulary
    ``did_you_mean`` draws from). Unspaced runs, pure numbers and words under
    ``SUGGEST_MIN_CHARS`` characters are left out."""
    text = _RUN.sub(" ", normalize(text))
    return {w for w in (t.casefold() for t in _TOKEN.findall(text)) if len(w) >= SUGGEST_MIN_CHARS and not w.isdigit()}


def edit_distance(a: str, b: str, limit: int) -> int:
    """Optimal string alignment distance (a swap of two adjacent characters costs 1), or
    ``limit + 1`` as soon as it is certain to exceed ``limit``."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev2: list[int] = []
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        if min(cur) > limit:
            return limit + 1
        prev2, prev = prev, cur
    return prev[-1] if prev[-1] <= limit else limit + 1


def _quote(term: str) -> str:
    return '"' + term.replace('"', '""') + '"'


@dataclass(frozen=True)
class QueryUnit:
    """One user-visible query word: a spaced-script word, or a whole unspaced run.

    ``terms`` are FTS5 expressions; a card earns ``matched / len(terms)`` credit for the
    unit. ``phrase`` (runs of 3+ units) is the run's contiguous bigram sequence; matching
    it means the card contains the run verbatim.
    """

    text: str
    terms: tuple[str, ...]
    phrase: str | None = None
    unspaced: bool = False


@dataclass(frozen=True)
class QueryPlan:
    units: tuple[QueryUnit, ...]

    @property
    def terms(self) -> list[str]:
        return list(dict.fromkeys(t for u in self.units for t in u.terms))

    @property
    def phrases(self) -> list[str]:
        return list(dict.fromkeys(u.phrase for u in self.units if u.phrase))

    @property
    def match_expression(self) -> str:
        return " OR ".join(self.terms)


def analyze_query(query: str) -> QueryPlan:
    """Turn free text into query units (always safe FTS5 syntax; ``word*`` = prefix)."""
    text = normalize(query)
    units: list[QueryUnit] = []
    seen: set[tuple[str, ...]] = set()

    def add(unit: QueryUnit) -> None:
        if unit.terms and unit.terms not in seen:
            seen.add(unit.terms)
            units.append(unit)

    def words(segment: str) -> None:
        for m in _WORD.finditer(segment):
            word = m.group(0).rstrip("*")
            if word:
                add(QueryUnit(word, (_quote(word) + ("*" if m.group(1) else ""),)))

    last = 0
    for m in _RUN.finditer(text):
        words(text[last : m.start()])
        run_units = _units(m.group())
        if len(run_units) == 1:
            add(QueryUnit(m.group(), (_quote(run_units[0]),), unspaced=True))
        else:
            grams = _bigrams(run_units)
            phrase = _quote(" ".join(grams)) if len(grams) > 1 else None
            add(QueryUnit(m.group(), tuple(dict.fromkeys(_quote(g) for g in grams)), phrase, unspaced=True))
        last = m.end()
    words(text[last:])
    return QueryPlan(tuple(units))


def analyzer_signature() -> str:
    """Identifies index-time analysis; a different value means the index must be rebuilt."""
    return f"{ANALYZER_VERSION}:unicode-{unicodedata.unidata_version}"
