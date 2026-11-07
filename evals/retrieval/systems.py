"""The engine under test and the comparison versions, each undoing one design decision.

``mindslice`` is the unmodified engine. Every other system patches exactly one choice back out,
for the duration of a run on its own fresh workspace, so the paired difference measures what that
choice is worth on this data:

* ``bm25-order``    - coverage-first ranking undone: results ordered by BM25 score alone.
* ``strict-phrase`` - CJK query runs must match verbatim (adjacent bigrams as one FTS5 phrase),
                      the approach basic-memory ships; OR-ed bigrams with coverage credit undone.
* ``v1-baseline``   - the engine as of commit bc0e7ac: no script-aware analysis, no NFKC, raw
                      ``unicode61`` tokens, BM25 ordering.
* ``unweighted-coverage`` - coverage-first ranking with every query word counted equally (the
                      ranking before the dev-informed IDF weighting; see PLAN.md's ledger).
"""

from __future__ import annotations

import re
from contextlib import ExitStack, contextmanager
from typing import Iterator
from unittest import mock

from mindslice import index as index_module
from mindslice.index import Hit
from mindslice.lexical import QueryPlan, QueryUnit, analyze_query

SYSTEMS = ("mindslice", "bm25-order", "unweighted-coverage", "strict-phrase", "v1-baseline")
BASELINE = "mindslice"

_V1_WORD = re.compile(r"\w+(\*)?", re.UNICODE)


def _bm25_order_rank(self, plan: QueryPlan, rows) -> list[Hit]:
    return [Hit(r, float(r["score"]) if plan.units else 0.0, 0.0, 0) for r in rows]


def _unweighted_coverage_rank(self, plan: QueryPlan, rows) -> list[Hit]:
    if not plan.units:
        return [Hit(r, 0.0, 0.0, 0) for r in rows]
    term_ids = {t: self._matching_ids(t) for t in plan.terms}
    phrase_ids = {p: self._matching_ids(p) for p in plan.phrases}
    hits = []
    for r in rows:
        credit, phrases = 0.0, 0
        for unit in plan.units:
            if unit.phrase and r["id"] in phrase_ids[unit.phrase]:
                credit, phrases = credit + 1.0, phrases + 1
                continue
            credit += sum(1 for t in unit.terms if r["id"] in term_ids[t]) / len(unit.terms)
        hits.append(Hit(r, float(r["score"]), credit / len(plan.units), phrases))
    return hits


def _strict_phrase_plan(query: str) -> QueryPlan:
    plan = analyze_query(query)
    return QueryPlan(tuple(QueryUnit(u.text, (u.phrase,), None, u.unspaced) if u.phrase else u for u in plan.units))


def _v1_plan(query: str) -> QueryPlan:
    units, seen = [], set()
    for m in _V1_WORD.finditer(query or ""):
        term = '"' + m.group(0).rstrip("*").replace('"', "") + '"' + ("*" if m.group(1) else "")
        if term not in seen:
            seen.add(term)
            units.append(QueryUnit(m.group(0), (term,)))
    return QueryPlan(tuple(units))


@contextmanager
def system(name: str) -> Iterator[None]:
    if name not in SYSTEMS:
        raise ValueError(f"unknown system {name!r}; choose from {', '.join(SYSTEMS)}")
    with ExitStack() as stack:
        if name in ("bm25-order", "v1-baseline"):
            stack.enter_context(mock.patch.object(index_module.Index, "_rank", _bm25_order_rank))
        if name == "unweighted-coverage":
            stack.enter_context(mock.patch.object(index_module.Index, "_rank", _unweighted_coverage_rank))
        if name == "strict-phrase":
            stack.enter_context(mock.patch.object(index_module, "analyze_query", _strict_phrase_plan))
        if name == "v1-baseline":
            stack.enter_context(mock.patch.object(index_module, "index_text", lambda text: text))
            stack.enter_context(mock.patch.object(index_module, "analyze_query", _v1_plan))
        yield
